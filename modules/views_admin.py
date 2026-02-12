import streamlit as st
import pandas as pd
import sqlite3
import os
from modules.database import get_connection, DB_FILE, perform_backup, get_available_backups, get_hash, get_active_period_info

def render_admin_view():
    # INFO O PERIODU
    curr_p, dl = get_active_period_info()
    st.info(f"📅 **AKTIVNO RAZDOBLJE:** {curr_p}  |  ⏳ **ROK:** {dl}")

    st.header("🛠️ Super Admin Panel")
    if st.session_state.get('role') != 'SuperAdmin': st.error("Access Denied"); return

    tab1, tab2 = st.tabs(["👥 Korisnici", "💾 Backup"])

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

    with tab2:
        if st.button("Backup"):
            perform_backup()
            st.success("Backup OK!")
        bs = get_available_backups()
        if bs:
            for b in bs:
                with open(b, "rb") as f:
                    st.download_button(f"Preuzmi {os.path.basename(b)}", f, file_name=os.path.basename(b))