import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
import sqlite3
import time
from datetime import datetime, date
from modules.database import get_connection, get_active_period_info, DB_FILE, get_hash

# 1. IMPORT SVIH POTREBNIH UTILS FUNKCIJA
from modules.utils import get_df_from_json, make_hashes, create_9box_grid, safe_load_json
# 2. IMPORT KONSTANTI ZA LIMITE
from modules.constants import MAX_TITLE_LENGTH, MAX_TEXT_LENGTH

def clean_excel_id(value):
    """Pomoćna funkcija za čišćenje ID-eva iz Excela."""
    if pd.isna(value) or str(value).lower() in ['nan', 'none', '', ' ']: return ""
    str_val = str(value).strip()
    return str_val[:-2] if str_val.endswith(".0") else str_val

def render_hr_view():
    conn = get_connection()
    current_period, deadline = get_active_period_info()
    company_id = st.session_state.get('company_id', 1)
    hr_username = st.session_state.get('username') # Treba nam za provjeru lozinke
    
    st.info(f"📅 **AKTIVNO RAZDOBLJE:** {current_period}  |  ⏳ **ROK:** {deadline if deadline else 'Nije definiran'}")
    
    # DOHVAT SVIH PODATAKA (MASTER)
    query_master = """
        SELECT e.kadrovski_broj, e.ime_prezime, e.radno_mjesto, e.department, 
               m.ime_prezime as 'Nadređeni Manager', e.is_manager, e.active, e.manager_id
        FROM employees_master e
        LEFT JOIN employees_master m ON e.manager_id = m.kadrovski_broj
        WHERE e.company_id = ?
    """
    df_master = pd.read_sql_query(query_master, conn, params=(company_id,))
    
    dept_list = ["Svi"]
    if not df_master.empty and 'department' in df_master.columns:
        unique_depts = df_master['department'].dropna().unique().tolist()
        dept_list += sorted(unique_depts)
    
    menu = st.sidebar.radio("HR Navigacija", [
        "📊 HR Dashboard", 
        "👤 Snail Trail (Povijest)", 
        "🎯 Upravljanje Ciljevima", 
        "🚀 Razvojni Planovi (IDP)", 
        "📋 Dizajner Upitnika", 
        "🗂️ Šifarnik & Unos", 
        "🛠️ Uređivanje & GDPR", 
        "⚙️ Postavke Razdoblja", 
        "📥 Export"
    ])

    # ----------------------------------------------------------------
    # 1. HR DASHBOARD
    # ----------------------------------------------------------------
    if menu == "📊 HR Dashboard":
        st.header(f"📊 HR Analitika")
        sel_dept = st.selectbox("Filtriraj po odjelu:", dept_list)
        
        # Prikaz samo 'Submitted' procjena
        df_ev = pd.read_sql_query("""
            SELECT ev.kadrovski_broj, ev.ime_prezime, ev.avg_performance, ev.avg_potential, ev.category, ev.is_self_eval, em.department 
            FROM evaluations ev
            JOIN employees_master em ON ev.kadrovski_broj = em.kadrovski_broj
            WHERE ev.period = ? AND ev.company_id = ? AND ev.status = 'Submitted'
        """, conn, params=(current_period, company_id))
        
        df_ev['avg_performance'] = pd.to_numeric(df_ev['avg_performance'], errors='coerce').fillna(0)
        df_ev['avg_potential'] = pd.to_numeric(df_ev['avg_potential'], errors='coerce').fillna(0)
        
        if sel_dept != "Svi":
            f_ev = df_ev[df_ev['department'].astype(str).str.strip() == str(sel_dept).strip()]
        else: f_ev = df_ev
        
        f_ev_mgr = f_ev[f_ev['is_self_eval'] == 0]
        
        t1, t2 = st.tabs(["9-Box Matrica", "Tablični Prikaz"])
        with t1:
            if not f_ev_mgr.empty:
                fig = create_9box_grid(f_ev_mgr, title=f"9-Box Distribucija ({sel_dept})")
                if fig: st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("Nema ZAKLJUČANIH službenih procjena za ovaj odjel/period.")
        with t2:
            if not f_ev_mgr.empty:
                st.dataframe(f_ev_mgr[['ime_prezime', 'department', 'avg_performance', 'avg_potential', 'category']], use_container_width=True)
            else: st.info("Nema podataka.")

    # ----------------------------------------------------------------
    # 2. SNAIL TRAIL
    # ----------------------------------------------------------------
    elif menu == "👤 Snail Trail (Povijest)":
        st.header("👤 Snail Trail - Razvoj kroz vrijeme")
        sel_emp = st.selectbox("Odaberi zaposlenika:", [f"{r['ime_prezime']} ({r['kadrovski_broj']})" for _, r in df_master.iterrows()])
        
        if sel_emp:
            eid = sel_emp.split("(")[1].replace(")", "")
            h = pd.read_sql_query("""
                SELECT period, avg_performance, avg_potential, category 
                FROM evaluations 
                WHERE kadrovski_broj=? AND is_self_eval=0 AND status='Submitted' 
                ORDER BY period ASC
            """, conn, params=(eid,))
            
            if not h.empty:
                c1, c2 = st.columns([3, 1])
                with c1:
                    fig = px.line(h, x="avg_performance", y="avg_potential", text="period", markers=True, title=f"Put razvoja: {sel_emp}")
                    fig.update_layout(
                        xaxis=dict(range=[0.5, 5.5], title="Učinak"), 
                        yaxis=dict(range=[0.5, 5.5], title="Potencijal"),
                        shapes=[
                            dict(type="line", x0=2.5, x1=2.5, y0=0, y1=6, line=dict(color="gray", width=1, dash="dot")),
                            dict(type="line", x0=4.0, x1=4.0, y0=0, y1=6, line=dict(color="gray", width=1, dash="dot")),
                            dict(type="line", x0=0, x1=6, y0=2.5, y1=2.5, line=dict(color="gray", width=1, dash="dot")),
                            dict(type="line", x0=0, x1=6, y0=4.0, y1=4.0, line=dict(color="gray", width=1, dash="dot")),
                        ]
                    )
                    st.plotly_chart(fig, use_container_width=True)
                with c2:
                    st.write("**Povijest ocjena:**")
                    st.dataframe(h[['period', 'category']], hide_index=True)
            else: st.info("Nema zaključanih povijesnih procjena.")

    # ----------------------------------------------------------------
    # 3. CILJEVI (Ažurirano s detaljnim KPI prikazom)
    # ----------------------------------------------------------------
    elif menu == "🎯 Upravljanje Ciljevima":
        st.header("🎯 Pregled ciljeva po organizaciji")
        sel_dept_g = st.selectbox("Odjel:", dept_list, key="goals_dept")
        filtered_master = df_master[df_master['department'] == sel_dept_g] if sel_dept_g != "Svi" else df_master

        if not filtered_master.empty:
            for _, emp in filtered_master.iterrows():
                eid = emp['kadrovski_broj']
                goals = pd.read_sql_query("SELECT * FROM goals WHERE kadrovski_broj=? AND period=?", conn, params=(eid, current_period))
                if not goals.empty:
                    with st.expander(f"👤 {emp['ime_prezime']} ({len(goals)} ciljeva)"):
                        for _, g in goals.iterrows():
                            # Prikaz zaglavlja cilja
                            st.markdown(f"**🎯 {g['title']}** (Težina: {g['weight']}%, Ostvareno: {g['progress']:.1f}%) | Rok: {g['deadline']}")
                            if str(g['description']).strip() and str(g['description']) != 'nan':
                                st.caption(f"Opis: {g['description']}")
                            
                            # Prikaz KPI-eva za cilj
                            kpis = pd.read_sql_query("SELECT description, weight, progress FROM goal_kpis WHERE goal_id=?", conn, params=(g['id'],))
                            if not kpis.empty:
                                st.dataframe(kpis.rename(columns={'description':'KPI (Ključni pokazatelj)', 'weight':'Težina (%)', 'progress':'Ostvarenje (%)'}), hide_index=True, use_container_width=True)
                            else:
                                st.caption("Nema definiranih KPI-eva za ovaj cilj.")
                            st.divider()
        else: st.info("Nema zaposlenika u odabranom odjelu.")

    # ----------------------------------------------------------------
    # 4. IDP (Ažurirano s punim detaljima i 70-20-10 tablicama)
    # ----------------------------------------------------------------
    elif menu == "🚀 Razvojni Planovi (IDP)":
        st.header("🚀 Pregled Razvojnih Planova (IDP)")
        sel_dept_idp = st.selectbox("Filtriraj po odjelu:", dept_list, key="idp_dept")
        f_m = df_master[df_master['department'] == sel_dept_idp] if sel_dept_idp != "Svi" else df_master
            
        if not f_m.empty:
            for _, emp in f_m.iterrows():
                eid = emp['kadrovski_broj']
                res = conn.execute("SELECT * FROM development_plans WHERE kadrovski_broj=? AND period=?", (eid, current_period)).fetchone()
                icon = "✅" if res else "❌"
                status_text = res[12] if res else "Nije kreiran" 
                
                with st.expander(f"{icon} {emp['ime_prezime']} ({emp['radno_mjesto']}) - {status_text}"):
                    if res:
                        cols = [c[1] for c in conn.execute("PRAGMA table_info(development_plans)").fetchall()]
                        d = dict(zip(cols, res))
                        st.write(f"**🎯 Karijerni cilj:** {d.get('career_goal')}")
                        c1, c2 = st.columns(2)
                        with c1: st.info(f"**Snage:**\n{d.get('strengths')}")
                        with c2: st.warning(f"**Područja za razvoj:**\n{d.get('areas_improve')}")
                        
                        st.markdown("---")
                        st.markdown("#### Akcijski plan (70-20-10)")
                        col_70, col_20, col_10 = st.columns(3)
                        
                        with col_70:
                            st.success("📌 70% Iskustvo")
                            df_70 = get_df_from_json(d.get('json_70'), ["Što razviti?", "Aktivnost", "Rok", "Dokaz"])
                            if not df_70.empty: st.dataframe(df_70, use_container_width=True, hide_index=True)
                            else: st.caption("Nema unosa.")
                            
                        with col_20:
                            st.warning("👥 20% Mentoring")
                            df_20 = get_df_from_json(d.get('json_20'), ["Što razviti?", "Aktivnost", "Rok"])
                            if not df_20.empty: st.dataframe(df_20, use_container_width=True, hide_index=True)
                            else: st.caption("Nema unosa.")
                            
                        with col_10:
                            st.error("📚 10% Edukacija")
                            df_10 = get_df_from_json(d.get('json_10'), ["Edukacija", "Trošak", "Rok"])
                            if not df_10.empty: st.dataframe(df_10, use_container_width=True, hide_index=True)
                            else: st.caption("Nema unosa.")
                            
                        st.markdown("---")
                        st.write(f"**Vrsta podrške:** {d.get('support_needed') if d.get('support_needed') else '---'}")
                        if d.get('support_notes'):
                            st.write(f"**Napomene:** {d.get('support_notes')}")
                    else: st.warning("Nema IDP-a.")
        else: st.info("Nema zaposlenika.")

    # ----------------------------------------------------------------
    # 5. DIZAJNER UPITNIKA
    # ----------------------------------------------------------------
    elif menu == "📋 Dizajner Upitnika":
        st.header("📋 Dizajner Upitnika")
        tab_tm, tab_q, tab_link = st.tabs(["1. Predlošci", "2. Pitanja", "3. Povezivanje"])
        
        with tab_tm:
            with st.form("new_template"):
                tn = st.text_input("Naziv novog predloška", max_chars=MAX_TITLE_LENGTH)
                td = st.text_area("Opis", max_chars=MAX_TEXT_LENGTH)
                if st.form_submit_button("➕ Kreiraj Predložak"):
                    if tn:
                        with sqlite3.connect(DB_FILE) as db:
                            db.execute("INSERT INTO form_templates (name, description, created_at, company_id) VALUES (?,?,?,?)", 
                                       (tn, td, datetime.now().strftime("%Y-%m-%d"), company_id))
                            db.commit()
                        st.success("Kreirano!"); time.sleep(0.5); st.rerun()
            
            st.divider()
            templates_all = pd.read_sql_query("SELECT * FROM form_templates WHERE company_id=?", conn, params=(company_id,))
            st.dataframe(templates_all)

            st.divider()
            st.subheader("📑 Kopiranje postojećeg predloška")
            if not templates_all.empty:
                c_copy, c_btn = st.columns([3, 1])
                src_tmpl = c_copy.selectbox("Odaberi predložak za kopiranje:", templates_all['name'].tolist(), key="src_copy")
                if c_btn.button("Kopiraj"):
                    src_id = templates_all[templates_all['name'] == src_tmpl]['id'].values[0]
                    with sqlite3.connect(DB_FILE) as db:
                        db.execute("""INSERT INTO form_templates (name, description, created_at, company_id)
                            SELECT name || ' (Copy)', description, ?, company_id 
                            FROM form_templates WHERE id=?""", (datetime.now().strftime("%Y-%m-%d"), int(src_id)))
                        new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                        db.execute("""INSERT INTO form_questions (template_id, section, title, description, criteria_desc, order_index, company_id)
                            SELECT ?, section, title, description, criteria_desc, order_index, company_id
                            FROM form_questions WHERE template_id=?""", (int(new_id), int(src_id)))
                        db.commit()
                    st.success(f"Kopirano! Novi predložak: {src_tmpl} (Copy)"); time.sleep(1); st.rerun()

        with tab_q:
            templates = pd.read_sql_query("SELECT * FROM form_templates WHERE company_id=?", conn, params=(company_id,))
            if not templates.empty:
                sel_tmpl_name = st.selectbox("Odaberi predložak za uređivanje:", templates['name'].tolist())
                tmpl_id = int(templates[templates['name'] == sel_tmpl_name]['id'].values[0])
                
                with st.form("add_q_form"):
                    c1, c2 = st.columns(2)
                    sect = c1.selectbox("Sekcija", ["Učinak (Performance)", "Potencijal (Potential)"])
                    sect_val = "p" if "Učinak" in sect else "pot"
                    q_t = c2.text_input("Pitanje", max_chars=MAX_TITLE_LENGTH)
                    q_d = st.text_area("Opis / Pomoć", max_chars=MAX_TEXT_LENGTH)
                    if st.form_submit_button("➕ Dodaj Pitanje"):
                        with sqlite3.connect(DB_FILE) as db:
                            db.execute("INSERT INTO form_questions (template_id, section, title, description, criteria_desc, company_id, order_index) VALUES (?,?,?,?,'',?,0)", 
                                       (tmpl_id, sect_val, q_t, q_d, company_id))
                            db.commit()
                        st.success("Dodano!"); st.rerun()
                st.dataframe(pd.read_sql_query("SELECT * FROM form_questions WHERE template_id=?", conn, params=(tmpl_id,)))

        with tab_link:
            st.info(f"Povezivanje upitnika s periodom: **{current_period}**")
            templates = pd.read_sql_query("SELECT * FROM form_templates WHERE company_id=?", conn, params=(company_id,))
            
            curr_active_tmpl = conn.execute("SELECT template_id FROM cycle_templates WHERE period_name=? AND company_id=?", (current_period, company_id)).fetchone()
            if curr_active_tmpl:
                act_name = conn.execute("SELECT name FROM form_templates WHERE id=?", (curr_active_tmpl[0],)).fetchone()
                st.success(f"Trenutno se koristi: **{act_name[0] if act_name else 'Nepoznato'}**")
            else: st.warning("Trenutno se koriste: **Default (Hardcoded) postavke**")

            if not templates.empty:
                s_t = st.selectbox("Odaberi novi aktivni upitnik:", templates['name'].tolist())
                tid = templates[templates['name']==s_t]['id'].values[0]
                
                c_act, c_reset = st.columns(2)
                if c_act.button("🔗 Aktiviraj za ovaj period"):
                    with sqlite3.connect(DB_FILE) as db:
                        db.execute("DELETE FROM cycle_templates WHERE period_name=? AND company_id=?", (current_period, company_id))
                        db.execute("INSERT INTO cycle_templates (period_name, template_id, company_id) VALUES (?,?,?)", (current_period, int(tid), company_id))
                        db.commit()
                    st.success("Aktivirano!"); time.sleep(1); st.rerun()
                
                if c_reset.button("🔄 Vrati na Default (Hardcoded)"):
                    with sqlite3.connect(DB_FILE) as db:
                        db.execute("DELETE FROM cycle_templates WHERE period_name=? AND company_id=?", (current_period, company_id))
                        db.commit()
                    st.success("Vraćeno na tvorničke postavke!"); time.sleep(1); st.rerun()

    # ----------------------------------------------------------------
    # 6. ŠIFARNIK I UNOS
    # ----------------------------------------------------------------
    elif menu == "🗂️ Šifarnik & Unos":
        st.header("🗂️ Upravljanje Zaposlenicima")
        t1, t2, t3 = st.tabs(["Popis", "Ručni Unos", "Excel Import"])
        
        with t1: st.dataframe(df_master, use_container_width=True)
        
        with t2:
            with st.form("manual_add"):
                c1, c2 = st.columns(2)
                kb = c1.text_input("Korisničko ime (ID)*", max_chars=20)
                ip = c2.text_input("Ime i Prezime*", max_chars=50)
                rm = c1.text_input("Radno mjesto", max_chars=50)
                od = c2.text_input("Odjel", max_chars=50)
                
                mgr_list = df_master[df_master['is_manager']==1]
                mgr_dict = dict(zip(mgr_list['ime_prezime'], mgr_list['kadrovski_broj']))
                sel_m = st.selectbox("Manager:", ["---"] + list(mgr_dict.keys()))
                sel_mid = mgr_dict.get(sel_m, "") if sel_m != "---" else ""
                is_m = st.checkbox("Je li Manager?")
                
                if st.form_submit_button("Spremi"):
                    if kb and ip:
                        if kb == sel_mid:
                            st.error("❌ Greška: Zaposlenik ne može biti sam sebi nadređeni!")
                        else:
                            pw = make_hashes("lozinka123")
                            with sqlite3.connect(DB_FILE) as db:
                                db.execute("INSERT OR REPLACE INTO employees_master (kadrovski_broj, ime_prezime, radno_mjesto, department, manager_id, is_manager, active, company_id) VALUES (?,?,?,?,?,?,?,?)", 
                                           (kb, ip, rm, od, sel_mid, 1 if is_m else 0, 1, company_id))
                                db.execute("INSERT OR IGNORE INTO users (username, password, role, department, company_id) VALUES (?,?,?,?,?)", 
                                           (kb, pw, "Manager" if is_m else "Employee", od, company_id))
                                db.commit()
                            st.success("Spremljeno!"); time.sleep(1); st.rerun()
                    else: st.error("Obavezna polja!")

        with t3:
            f = st.file_uploader("Excel Import", type=['xlsx'])
            if f and st.button("Import"):
                try:
                    df_i = pd.read_excel(f)
                    pw = make_hashes("lozinka123")
                    with sqlite3.connect(DB_FILE) as db:
                        for _, r in df_i.iterrows():
                            kid = clean_excel_id(r.get('kadrovski_broj'))
                            if not kid: continue
                            mid = clean_excel_id(r.get('manager_id'))
                            im = 1 if str(r.get('is_manager')).lower() in ['da','1','true'] else 0
                            db.execute("INSERT OR REPLACE INTO employees_master (kadrovski_broj, ime_prezime, radno_mjesto, department, manager_id, is_manager, active, company_id) VALUES (?,?,?,?,?,?,?,?)", 
                                       (kid, r.get('ime_prezime'), r.get('radno_mjesto'), r.get('department'), mid, im, 1, company_id))
                            db.execute("INSERT OR IGNORE INTO users (username, password, role, department, company_id) VALUES (?,?,?,?,?)", 
                                       (kid, pw, "Manager" if im else "Employee", r.get('department'), company_id))
                        db.commit()
                    st.success("Import završen."); st.rerun()
                except Exception as e: st.error(str(e))

    # ----------------------------------------------------------------
    # 7. UREĐIVANJE & BRISANJE (SADA S GDPR-om)
    # ----------------------------------------------------------------
    elif menu == "🛠️ Uređivanje & GDPR":
        st.header("🛠️ Administracija")
        sel_e = st.selectbox("Djelatnik:", ["---"] + [f"{r['ime_prezime']} ({r['kadrovski_broj']})" for _, r in df_master.iterrows()])
        
        if sel_e != "---":
            real_id = sel_e.split("(")[-1].replace(")", "")
            curr = df_master[df_master['kadrovski_broj'] == real_id].iloc[0]
            
            # --- DIO 1: UREĐIVANJE ---
            with st.form("edit_emp"):
                st.subheader(f"Uređivanje: {curr['ime_prezime']}")
                c1, c2 = st.columns(2)
                n_ime = c1.text_input("Ime i Prezime", value=curr['ime_prezime'], max_chars=50)
                n_dept = c2.text_input("Odjel", value=curr['department'], max_chars=50)
                
                mgr_list = df_master[df_master['is_manager']==1]
                mgr_dict = dict(zip(mgr_list['ime_prezime'], mgr_list['kadrovski_broj']))
                curr_mgr_name = "---"
                if curr['manager_id']:
                    m_res = df_master[df_master['kadrovski_broj'] == curr['manager_id']]
                    if not m_res.empty: curr_mgr_name = m_res.iloc[0]['ime_prezime']
                
                options = ["---"] + list(mgr_dict.keys())
                try: def_idx = options.index(curr_mgr_name)
                except: def_idx = 0
                
                sel_mgr_name = st.selectbox("Nadređeni:", options, index=def_idx)
                n_pass = st.text_input("Nova Lozinka (ostavi prazno ako ne mijenjaš)")
                
                # NOVO: Status toggle
                is_active = st.checkbox("Aktivan Korisnik", value=(curr['active'] == 1))
                
                if st.form_submit_button("Spremi Promjene"):
                    new_mgr_id = mgr_dict.get(sel_mgr_name, "") if sel_mgr_name != "---" else ""
                    if new_mgr_id == real_id:
                        st.error("❌ Greška: Zaposlenik ne može biti sam sebi nadređeni!")
                    else:
                        with sqlite3.connect(DB_FILE) as db:
                            # Update uključuje i active status
                            db.execute("UPDATE employees_master SET ime_prezime=?, department=?, manager_id=?, active=? WHERE kadrovski_broj=?", 
                                       (n_ime, n_dept, new_mgr_id, 1 if is_active else 0, real_id))
                            db.execute("UPDATE users SET department=? WHERE username=?", (n_dept, real_id))
                            if n_pass:
                                db.execute("UPDATE users SET password=? WHERE username=?", (make_hashes(n_pass), real_id))
                            db.commit()
                        st.success("Podaci uspješno ažurirani!"); time.sleep(1); st.rerun()

            st.divider()
            
            # --- DIO 2: OPASNA ZONA (GDPR & DELETE) ---
            st.error("⚠️ Opasna Zona")
            c_gdpr, c_del = st.columns(2)
            
            # A) GDPR ANONIMIZACIJA
            with c_gdpr:
                st.subheader("🕵️ GDPR Anonimizacija")
                st.caption("Mijenja ime u 'Anonymized', briše komentare, ali zadržava ocjene radi statistike. Deaktivira korisnika.")
                if st.button("Anonimiziraj korisnika"):
                    with sqlite3.connect(DB_FILE) as db:
                        # 1. Update Master
                        new_anon_name = f"Anonymized_{real_id}"
                        db.execute("UPDATE employees_master SET ime_prezime=?, active=0 WHERE kadrovski_broj=?", (new_anon_name, real_id))
                        # 2. Sanitize Evaluations (Briše tekst, ostavlja brojeve)
                        db.execute("UPDATE evaluations SET action_plan='[GDPR Cleared]', json_answers='{}' WHERE kadrovski_broj=?", (real_id,))
                        # 3. Clear Goals Text
                        db.execute("UPDATE goals SET description='[GDPR Cleared]', title='[GDPR Cleared]' WHERE kadrovski_broj=?", (real_id,))
                        # 4. Clear IDP
                        db.execute("UPDATE development_plans SET strengths='', areas_improve='', career_goal='[GDPR]', support_notes='' WHERE kadrovski_broj=?", (real_id,))
                        db.commit()
                    st.success("Korisnik anonimiziran!"); time.sleep(1); st.rerun()

            # B) HARD DELETE (S POTVRDOM LOZINKE)
            with c_del:
                st.subheader("🗑️ Trajno Brisanje")
                st.caption("Briše SVE podatke o korisniku nepovratno. Zahtijeva potvrdu lozinkom trenutnog HR administratora.")
                
                del_pass = st.text_input("Unesite SVOJU lozinku za potvrdu:", type="password")
                
                if st.button("TRAJNO OBRIŠI"):
                    # 1. Provjera lozinke trenutnog admina
                    pwd_hash = get_hash(del_pass)
                    
                    # Provjeravamo je li unio dobru lozinku za sebe (hr_username)
                    check_conn = get_connection()
                    res = check_conn.execute("SELECT * FROM users WHERE username=? AND password=?", (hr_username, pwd_hash)).fetchone()
                    check_conn.close()
                    
                    if res:
                        with sqlite3.connect(DB_FILE) as db:
                            for tbl in ['employees_master', 'users', 'evaluations', 'goals', 'development_plans']:
                                col = 'username' if tbl == 'users' else 'kadrovski_broj'
                                db.execute(f"DELETE FROM {tbl} WHERE {col}=?", (real_id,))
                            db.commit()
                        st.success("Korisnik trajno obrisan!"); time.sleep(1); st.rerun()
                    else:
                        st.error("Neispravna lozinka! Brisanje odbijeno.")

    # ----------------------------------------------------------------
    # 8. POSTAVKE RAZDOBLJA
    # ----------------------------------------------------------------
    elif menu == "⚙️ Postavke Razdoblja":
        st.header("⚙️ Postavke Razdoblja")
        t1, t2, t3 = st.tabs(["Aktivacija / Promjena", "Novo Razdoblje", "Brisanje"])
        
        with t1:
            periods = pd.read_sql_query("SELECT period_name, start_date, deadline, is_active FROM periods WHERE company_id=? ORDER BY period_name DESC", conn, params=(company_id,))
            if not periods.empty:
                st.dataframe(periods, use_container_width=True)
                active_row = periods[periods['is_active'] == 1]
                curr_active = active_row.iloc[0]['period_name'] if not active_row.empty else "Nema aktivnog"
                st.info(f"Trenutno aktivno: **{curr_active}**")
                
                sel_activate = st.selectbox("Postavi novo aktivno razdoblje:", periods['period_name'].tolist())
                if st.button("✅ Aktiviraj odabrano"):
                    with sqlite3.connect(DB_FILE) as db:
                        db.execute("UPDATE periods SET is_active=0 WHERE company_id=?", (company_id,))
                        db.execute("UPDATE periods SET is_active=1 WHERE period_name=? AND company_id=?", (sel_activate, company_id))
                        db.execute("UPDATE app_settings SET setting_value=? WHERE setting_key='active_period'", (sel_activate,))
                        db.commit()
                    st.success(f"Razdoblje {sel_activate} je sada aktivno!"); time.sleep(1); st.rerun()
                
                st.divider()
                new_deadline = st.date_input("Novi rok")
                if st.button("💾 Ažuriraj Rok"):
                    with sqlite3.connect(DB_FILE) as db:
                        db.execute("UPDATE periods SET deadline=? WHERE period_name=?", (str(new_deadline), sel_activate))
                        db.commit()
                    st.success("Rok ažuriran."); st.rerun()

        with t2:
            with st.form("create_p"):
                np = st.text_input("Naziv (npr. 2025-Q2)", max_chars=20)
                sd = st.date_input("Datum početka")
                ed = st.date_input("Rok završetka")
                if st.form_submit_button("Spremi"):
                    if np:
                        with sqlite3.connect(DB_FILE) as db:
                            db.execute("INSERT INTO periods (period_name, start_date, deadline, is_active, company_id) VALUES (?,?,?,0,?)", (np, str(sd), str(ed), company_id))
                            db.commit()
                        st.success("Kreirano!"); time.sleep(1); st.rerun()

        with t3:
            if not periods.empty:
                p_del = st.selectbox("Odaberi razdoblje za brisanje:", periods['period_name'].tolist())
                confirm = st.checkbox(f"Siguran sam da želim obrisati {p_del}?", value=False)
                if st.button("🗑️ Obriši"):
                    if confirm:
                        with sqlite3.connect(DB_FILE) as db:
                            db.execute("DELETE FROM periods WHERE period_name=?", (p_del,))
                            db.commit()
                        st.success("Obrisano!"); time.sleep(1); st.rerun()
                    else: st.error("Molimo potvrdite brisanje.")

    # ----------------------------------------------------------------
    # 9. EXPORT
    # ----------------------------------------------------------------
    elif menu == "📥 Export":
        st.header("📥 Export")
        st.caption("Preuzimanje podataka za arhivu i analizu.")
        if st.button("Preuzmi Excel"):
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                pd.read_sql_query("SELECT * FROM employees_master WHERE company_id=?", conn, params=(company_id,)).to_excel(writer, sheet_name="Zaposlenici")
                
                # Privacy Filter
                pd.read_sql_query("""
                    SELECT * FROM evaluations 
                    WHERE company_id=? AND (status='Submitted' OR is_self_eval=1)
                """, conn, params=(company_id,)).to_excel(writer, sheet_name="Procjene")
                
                pd.read_sql_query("SELECT * FROM goals WHERE company_id=?", conn, params=(company_id,)).to_excel(writer, sheet_name="Ciljevi")
                pd.read_sql_query("SELECT * FROM development_plans WHERE company_id=?", conn, params=(company_id,)).to_excel(writer, sheet_name="IDP")
            st.download_button("Download", buffer.getvalue(), f"export_hr_{date.today()}.xlsx")

    conn.close()