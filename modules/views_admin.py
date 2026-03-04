import streamlit as st
import pandas as pd
import sqlite3
import os
from modules.database import get_connection, DB_FILE, perform_backup, get_available_backups, get_hash, get_active_period_info, log_action

def render_admin_view():
    # INFO O PERIODU
    curr_p, dl = get_active_period_info()
    st.info(f"📅 **AKTIVNO RAZDOBLJE:** {curr_p}  |  ⏳ **ROK:** {dl}")

    st.header("🛠️ Super Admin Panel")
    if st.session_state.get('role') != 'SuperAdmin': 
        st.error("Access Denied")
        return

    tab1, tab2, tab3, tab4 = st.tabs(["👥 Korisnici", "🚨 Panic Button", "📜 Audit Log", "💾 Backup"])

    # ---------------------------------------------------------
    # TAB 1: UPRAVLJANJE KORISNICIMA
    # ---------------------------------------------------------
    with tab1:
        st.subheader("Popravak Korisničkih Računa")
        
        c1, c2 = st.columns(2)
        
        with c1:
            st.info("Opcija A: Sigurna sinkronizacija. Kreira račun SAMO onima koji ga nemaju. Ne dira postojeće lozinke.")
            if st.button("✅ Sigurna Sinkronizacija"):
                pw_hash = get_hash("lozinka123")
                with sqlite3.connect(DB_FILE) as db:
                    emps = db.execute("SELECT kadrovski_broj, department, is_manager FROM employees_master WHERE kadrovski_broj != 'admin'").fetchall()
                    c = 0
                    for e in emps:
                        kid = str(e[0]).strip()
                        role = "Manager" if e[2] else "Employee"
                        db.execute("INSERT OR IGNORE INTO users (username, password, role, department, company_id) VALUES (?,?,?,?,1)", (kid, pw_hash, role, e[1]))
                        if db.total_changes > 0: c += 1
                    db.commit()
                st.success(f"Kreirano {c} novih računa.")

        with c2:
            st.error("Opcija B: Potpuni Reset. Svima (osim admina) resetira lozinku na 'lozinka123'.")
            if st.button("⚠️ RESETIRAJ SVE LOZINKE"):
                pw_hash = get_hash("lozinka123")
                with sqlite3.connect(DB_FILE) as db:
                    emps = db.execute("SELECT kadrovski_broj, department, is_manager FROM employees_master WHERE kadrovski_broj != 'admin'").fetchall()
                    for e in emps:
                        kid = str(e[0]).strip()
                        role = "Manager" if e[2] else "Employee"
                        db.execute("INSERT OR REPLACE INTO users (username, password, role, department, company_id) VALUES (?,?,?,?,1)", (kid, pw_hash, role, e[1]))
                    db.commit()
                st.success("Sve lozinke resetirane na 'lozinka123'!")

        st.divider()
        users = pd.read_sql_query("SELECT username, role, department FROM users", get_connection())
        st.dataframe(users)

    # ---------------------------------------------------------
    # TAB 2: PANIC BUTTON (SADA SA SELECTBOX-om)
    # ---------------------------------------------------------
    with tab2:
        st.subheader("🚨 Hitna intervencija: Otključavanje procjene")
        st.markdown("""
            Ovaj alat služi za **vraćanje zaključane procjene (Submitted) natrag u Draft status**.
            Koristite ovo samo kada je manager greškom zaključao procjenu prije vremena.
        """)
        
        # --- NOVO: Dohvat liste perioda za dropdown ---
        conn = get_connection()
        try:
            periods_res = conn.execute("SELECT period_name FROM periods ORDER BY period_name DESC").fetchall()
            period_opts = [p[0] for p in periods_res]
        except:
            period_opts = []
        conn.close()
        # ---------------------------------------------
        
        with st.form("panic_form"):
            c1, c2 = st.columns(2)
            target_id = c1.text_input("Kadrovski broj zaposlenika (ID)")
            
            # --- NOVO: Selectbox umjesto Text Input ---
            target_period = c2.selectbox("Period", period_opts)
            
            reason = st.text_area("Razlog intervencije (Obavezno za logiranje)")
            
            if st.form_submit_button("🔓 OTKLJUČAJ (Vrati na Draft)"):
                if target_id and target_period and reason:
                    conn = get_connection()
                    
                    # 1. Provjera
                    check = conn.execute("SELECT status FROM evaluations WHERE kadrovski_broj=? AND period=?", (target_id, target_period)).fetchone()
                    
                    if not check:
                        st.error("❌ Procjena ne postoji za ovog zaposlenika i odabrani period.")
                    elif check[0] != 'Submitted':
                        st.warning(f"⚠️ Ova procjena nije zaključana. Trenutni status: {check[0]}")
                    else:
                        # 2. Update
                        conn.execute("UPDATE evaluations SET status='Draft' WHERE kadrovski_broj=? AND period=?", (target_id, target_period))
                        conn.commit()
                        
                        # 3. Log
                        admin_user = st.session_state.get('username', 'Unknown')
                        log_msg = f"Otkljucao procjenu za {target_id} ({target_period}). Razlog: {reason}"
                        cid = st.session_state.get('company_id', 1)
                        log_action(admin_user, "PANIC_UNLOCK", log_msg, cid)
                        
                        st.success(f"✅ Uspjeh! Procjena za {target_id} je vraćena u 'Draft'. Manager sada može ponovno uređivati.")
                    
                    conn.close()
                else:
                    st.error("Molimo ispunite sva polja, uključujući razlog.")

    # ---------------------------------------------------------
    # TAB 3: AUDIT LOG
    # ---------------------------------------------------------
    with tab3:
        st.subheader("📜 Pregled sistemskih akcija (Audit Log)")
        if st.button("Osvježi logove"):
            conn = get_connection()
            try:
                logs = pd.read_sql_query("SELECT * FROM action_logs ORDER BY timestamp DESC LIMIT 100", conn)
                st.dataframe(logs, use_container_width=True)
            except Exception as e:
                st.warning("Tablica 'action_logs' možda još nije kreirana ili je prazna.")
            conn.close()

    # ---------------------------------------------------------
    # TAB 4: BACKUP
    # ---------------------------------------------------------
    with tab4:
        if st.button("Napravi Backup Baze"):
            perform_backup()
            st.success("Backup uspješno kreiran!")
            
        st.write("Dostupne kopije:")
        bs = get_available_backups()
        if bs:
            for b in bs:
                with open(b, "rb") as f:
                    st.download_button(f"Preuzmi {os.path.basename(b)}", f, file_name=os.path.basename(b))
        else:
            st.info("Nema backup datoteka.")