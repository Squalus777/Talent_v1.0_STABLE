import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io
import sqlite3
import hashlib
import time
from datetime import datetime, date
from modules.database import get_connection, get_active_period_info, DB_FILE, get_hash
from modules.utils import get_df_from_json

def clean_excel_id(value):
    if pd.isna(value) or str(value).lower() in ['nan', 'none', '', ' ']: return ""
    str_val = str(value).strip()
    return str_val[:-2] if str_val.endswith(".0") else str_val

def render_hr_view():
    # Učitavamo konekciju i podatke
    conn = get_connection()
    current_period, deadline = get_active_period_info()
    company_id = st.session_state.get('company_id', 1)
    
    # INFO BAR
    st.info(f"📅 **AKTIVNO RAZDOBLJE:** {current_period}  |  ⏳ **ROK:** {deadline if deadline else 'Nije definiran'}")
    
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
        "📊 HR Dashboard", "👤 Snail Trail (Povijest)", "🎯 Upravljanje Ciljevima", 
        "🚀 Razvojni Planovi (IDP)", "📋 Dizajner Upitnika", "🗂️ Šifarnik & Unos", 
        "🛠️ Uređivanje Podataka", "⚙️ Postavke Razdoblja", "📥 Export"
    ])

    if menu == "📊 HR Dashboard":
        st.header(f"📊 HR Analitika")
        df_ev = pd.read_sql_query("""
            SELECT ev.kadrovski_broj, ev.ime_prezime, ev.avg_performance, ev.avg_potential, ev.category, ev.is_self_eval, em.department 
            FROM evaluations ev
            JOIN employees_master em ON ev.kadrovski_broj = em.kadrovski_broj
            WHERE ev.period = ? AND ev.company_id = ?
        """, conn, params=(current_period, company_id))
        
        df_ev['avg_performance'] = pd.to_numeric(df_ev['avg_performance'], errors='coerce').fillna(0)
        df_ev['avg_potential'] = pd.to_numeric(df_ev['avg_potential'], errors='coerce').fillna(0)
        df_ev['Tip'] = df_ev['is_self_eval'].apply(lambda x: 'Samoprocjena' if x==1 else 'Službena procjena')
        
        sel_dept = st.selectbox("Filtriraj po odjelu:", dept_list)
        if sel_dept != "Svi":
            f_ev = df_ev[df_ev['department'].astype(str).str.strip() == str(sel_dept).strip()]
        else: f_ev = df_ev
        
        if not f_ev.empty:
            fig = px.scatter(f_ev, x="avg_performance", y="avg_potential", color="Tip",
                             hover_data=["ime_prezime", "category"], text="ime_prezime", 
                             range_x=[0, 5.5], range_y=[0, 5.5], title="9-Box Distribucija")
            fig.add_vline(x=2.5, line_dash="dot", line_color="gray"); fig.add_vline(x=4.0, line_dash="dot", line_color="gray")
            fig.add_hline(y=2.5, line_dash="dot", line_color="gray"); fig.add_hline(y=4.0, line_dash="dot", line_color="gray")
            st.plotly_chart(fig, use_container_width=True)
        else: st.warning("Nema podataka.")

    elif menu == "👤 Snail Trail (Povijest)":
        st.header("👤 Snail Trail - Kretanje kroz vrijeme")
        st.caption("Prikaz kako se zaposlenik pomicao kroz 9-Box matricu kroz različita razdoblja.")
        
        sel_emp = st.selectbox("Djelatnik:", [f"{r['ime_prezime']} ({r['kadrovski_broj']})" for _, r in df_master.iterrows()])
        if sel_emp:
            eid = sel_emp.split("(")[1].replace(")", "")
            h = pd.read_sql_query("SELECT period, avg_performance, avg_potential, category FROM evaluations WHERE kadrovski_broj=? AND is_self_eval=0 ORDER BY period ASC", conn, params=(eid,))
            
            if not h.empty:
                # PRAVI SNAIL TRAIL
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=h['avg_performance'], y=h['avg_potential'],
                    mode='lines+markers+text',
                    text=h['period'], textposition="top center",
                    marker=dict(size=12, color='blue'),
                    line=dict(color='rgba(0,0,255,0.3)', width=2, dash='dot'),
                    name='Putanja'
                ))
                fig.update_layout(
                    title=f"Razvojni put: {sel_emp}",
                    xaxis=dict(title="Učinak", range=[0.5, 5.5]),
                    yaxis=dict(title="Potencijal", range=[0.5, 5.5]),
                    shapes=[
                        dict(type="line", x0=2.5, x1=2.5, y0=0, y1=6, line=dict(color="gray", width=1, dash="dot")),
                        dict(type="line", x0=4.0, x1=4.0, y0=0, y1=6, line=dict(color="gray", width=1, dash="dot")),
                        dict(type="line", x0=0, x1=6, y0=2.5, y1=2.5, line=dict(color="gray", width=1, dash="dot")),
                        dict(type="line", x0=0, x1=6, y0=4.0, y1=4.0, line=dict(color="gray", width=1, dash="dot")),
                    ]
                )
                st.plotly_chart(fig, use_container_width=True)
                st.table(h)
            else: st.info("Nema povijesnih podataka (službenih procjena).")

    elif menu == "🎯 Upravljanje Ciljevima":
        st.header("🎯 Detaljni pregled ciljeva")
        f_dept = st.selectbox("Odjel:", dept_list, key="g_dept")
        f_m = df_master if f_dept == "Svi" else df_master[df_master['department'] == f_dept]
        for _, emp in f_m.iterrows():
            eid = emp['kadrovski_broj']
            goals = pd.read_sql_query("SELECT * FROM goals WHERE kadrovski_broj=? AND period=?", conn, params=(eid, current_period))
            if not goals.empty:
                with st.expander(f"👤 {emp['ime_prezime']} ({len(goals)} ciljeva)"):
                    for _, g in goals.iterrows():
                        st.write(f"**{g['title']}** ({g['weight']}%) - `{g['status']}`")
                        st.progress(float(g['progress'])/100 if g['progress'] else 0.0)
                        kpis = pd.read_sql_query("SELECT description, weight, progress FROM goal_kpis WHERE goal_id=?", conn, params=(g['id'],))
                        if not kpis.empty: st.dataframe(kpis, use_container_width=True, hide_index=True)

    elif menu == "🚀 Razvojni Planovi (IDP)":
        st.header("🚀 Puni IDP Obrazac")
        f_dept = st.selectbox("Odjel:", dept_list, key="idp_f")
        f_m = df_master if f_dept == "Svi" else df_master[df_master['department'] == f_dept]
        for _, emp in f_m.iterrows():
            eid = emp['kadrovski_broj']
            res = conn.execute("SELECT * FROM development_plans WHERE kadrovski_broj=? AND period=?", (eid, current_period)).fetchone()
            tag = "✅ ISPUNJEN" if res else "❌ NEDOSTAJE"
            with st.expander(f"{tag} | {emp['ime_prezime']} ({emp['radno_mjesto']})"):
                if res:
                    cols = [c[1] for c in conn.execute("PRAGMA table_info(development_plans)").fetchall()]
                    d = dict(zip(cols, res))
                    st.subheader("1. Dijagnoza i Karijerni cilj")
                    st.write(f"**Glavni karijerni cilj:** {d.get('career_goal')}")
                    c1, c2 = st.columns(2)
                    c1.info(f"**Snage:**\n\n{d.get('strengths')}")
                    c2.warning(f"**Područja za razvoj:**\n\n{d.get('areas_improve')}")
                    st.subheader("2. Akcijski plan")
                    st.write("**70% Iskustvo:**"); st.dataframe(get_df_from_json(d.get('json_70'), ["Što?", "Aktivnost", "Rok", "Dokaz"]), use_container_width=True)
                    st.write("**20% Mentoring:**"); st.dataframe(get_df_from_json(d.get('json_20'), ["Što?", "Aktivnost", "Rok"]), use_container_width=True)
                    st.write("**10% Edukacija:**"); st.dataframe(get_df_from_json(d.get('json_10'), ["Edukacija", "Trošak", "Rok"]), use_container_width=True)
                    st.subheader("3. Podrška")
                    st.success(f"**Potrebno:** {d.get('support_needed')}")
                else: st.info("IDP nije kreiran.")

    elif menu == "📋 Dizajner Upitnika":
        st.header("📋 Dizajner Upitnika")
        tab_tm, tab_q, tab_link = st.tabs(["1. Predlošci", "2. Pitanja", "3. Povezivanje"])
        with tab_tm:
            with st.form("new_template"):
                tn = st.text_input("Naziv novog predloška")
                td = st.text_area("Opis")
                if st.form_submit_button("➕ Kreiraj Predložak"):
                    if tn:
                        with sqlite3.connect(DB_FILE) as db:
                            db.execute("INSERT INTO form_templates (name, description, created_at, company_id) VALUES (?,?,?,?)", (tn, td, datetime.now().strftime("%Y-%m-%d"), company_id))
                            db.commit()
                        st.success("Kreirano!"); st.rerun()
            st.markdown("---")
            templates = pd.read_sql_query("SELECT * FROM form_templates WHERE company_id=?", conn, params=(company_id,))
            if not templates.empty:
                for _, tm in templates.iterrows():
                    with st.expander(f"📂 {tm['name']} (ID: {tm['id']})"):
                        with st.form(f"edit_tm_{tm['id']}"):
                            un = st.text_input("Naziv", tm['name'])
                            ud = st.text_area("Opis", tm['description'])
                            c1, c3 = st.columns(2)
                            if c1.form_submit_button("💾 Spremi"):
                                with sqlite3.connect(DB_FILE) as db:
                                    db.execute("UPDATE form_templates SET name=?, description=? WHERE id=?", (un, ud, tm['id']))
                                    db.commit()
                                st.success("Ažurirano!"); st.rerun()
                            if c3.form_submit_button("🗑️ Obriši"):
                                with sqlite3.connect(DB_FILE) as db:
                                    db.execute("DELETE FROM form_questions WHERE template_id=?", (tm['id'],))
                                    db.execute("DELETE FROM form_templates WHERE id=?", (tm['id'],))
                                    db.commit()
                                st.warning("Obrisano!"); st.rerun()
        with tab_q:
            templates = pd.read_sql_query("SELECT * FROM form_templates WHERE company_id=?", conn, params=(company_id,))
            if not templates.empty:
                sel_tmpl_name = st.selectbox("Odaberi predložak:", templates['name'].tolist())
                tmpl_id = int(templates[templates['name'] == sel_tmpl_name]['id'].values[0])
                with st.form("add_q_form"):
                    c1, c2 = st.columns(2)
                    sect = c1.selectbox("Sekcija", ["Učinak", "Potencijal"])
                    sect_val = "p" if "Učinak" in sect else "pot"
                    q_t = c2.text_input("Naslov")
                    q_d = st.text_area("Opis")
                    if st.form_submit_button("➕ Dodaj"):
                        with sqlite3.connect(DB_FILE) as db:
                            db.execute("INSERT INTO form_questions (template_id, section, title, description, criteria_desc, company_id, order_index) VALUES (?,?,?,?,'',?,0)", (tmpl_id, sect_val, q_t, q_d, company_id))
                            db.commit()
                        st.success("Dodano!"); st.rerun()
                qs = pd.read_sql_query("SELECT * FROM form_questions WHERE template_id=?", conn, params=(tmpl_id,))
                for _, q in qs.iterrows():
                    with st.expander(f"{q['title']}"):
                        st.write(q['description'])
                        if st.button("Obriši", key=f"del_{q['id']}"):
                            with sqlite3.connect(DB_FILE) as db:
                                db.execute("DELETE FROM form_questions WHERE id=?", (q['id'],))
                                db.commit()
                            st.rerun()
        with tab_link:
            st.write(f"Period: **{current_period}**")
            templates = pd.read_sql_query("SELECT * FROM form_templates WHERE company_id=?", conn, params=(company_id,))
            if not templates.empty:
                s_t = st.selectbox("Upitnik:", templates['name'].tolist())
                tid = templates[templates['name']==s_t]['id'].values[0]
                if st.button("Aktiviraj"):
                    with sqlite3.connect(DB_FILE) as db:
                        db.execute("DELETE FROM cycle_templates WHERE period_name=? AND company_id=?", (current_period, company_id))
                        db.execute("INSERT INTO cycle_templates (period_name, template_id, company_id) VALUES (?,?,?)", (current_period, int(tid), company_id))
                        db.commit()
                    st.success("Aktivirano!"); st.rerun()

    elif menu == "🗂️ Šifarnik & Unos":
        st.header("🗂️ Upravljanje Zaposlenicima")
        t1, t2, t3 = st.tabs(["📋 Popis", "➕ Ručni Unos", "📥 Excel Import"])
        
        with t1: st.dataframe(df_master.drop(columns=['manager_id'], errors='ignore'), use_container_width=True)
        
        with t2:
            with st.form("manual_add"):
                c1, c2 = st.columns(2)
                kb = c1.text_input("Kadrovski broj*")
                ip = c2.text_input("Ime i Prezime*")
                rm = c1.text_input("Radno mjesto"); od = c2.text_input("Odjel")
                mgr_ops = {f"{r['ime_prezime']}": r['kadrovski_broj'] for _, r in df_master[df_master['is_manager']==1].iterrows()}
                sel_m = st.selectbox("Procjenitelj:", ["---"] + list(mgr_ops.keys()))
                is_m = st.radio("Procjenitelj?", ["NE", "DA"], horizontal=True)
                
                if st.form_submit_button("Spremi"):
                    if kb and ip:
                        role = "Manager" if is_m == "DA" else "Employee"
                        pw_hash = get_hash("lozinka123")
                        with sqlite3.connect(DB_FILE) as db:
                            db.execute("INSERT INTO employees_master (kadrovski_broj, ime_prezime, radno_mjesto, department, manager_id, is_manager, active, company_id) VALUES (?,?,?,?,?,?,?,?)", (kb, ip, rm, od, mgr_ops.get(sel_m, ""), 1 if is_m == "DA" else 0, 1, company_id))
                            db.execute("INSERT OR IGNORE INTO users (username, password, role, department, company_id) VALUES (?,?,?,?,?)", (kb, pw_hash, role, od, company_id))
                            db.commit()
                        st.success(f"Dodano! Ako je novi, lozinka je 'lozinka123'."); st.rerun()

        with t3:
            f = st.file_uploader("Excel file", type=['xlsx'])
            if f and st.button("Pokreni Import"):
                try:
                    df_i = pd.read_excel(f)
                    pw_hash = get_hash("lozinka123")
                    with sqlite3.connect(DB_FILE) as db:
                        cnt = 0
                        for _, r in df_i.iterrows():
                            kid = clean_excel_id(r['kadrovski_broj'])
                            if not kid: continue
                            mgr_id = clean_excel_id(r['manager_id']) if 'manager_id' in r else ""
                            is_mgr = 1 if str(r.get('is_manager','')).upper()=='DA' else 0
                            role = "Manager" if is_mgr else "Employee"
                            
                            db.execute("INSERT OR REPLACE INTO employees_master (kadrovski_broj, ime_prezime, radno_mjesto, department, manager_id, is_manager, active, company_id) VALUES (?,?,?,?,?,?,?,?)", (kid, r['ime_prezime'], r['radno_mjesto'], r['department'], mgr_id, is_mgr, 1, company_id))
                            db.execute("INSERT OR IGNORE INTO users (username, password, role, department, company_id) VALUES (?,?,?,?,?)", (kid, pw_hash, role, r['department'], company_id))
                            db.execute("UPDATE users SET role=?, department=? WHERE username=?", (role, r['department'], kid))
                            cnt += 1
                        db.commit()
                    st.success(f"Importirano {cnt} redova. Novi korisnici su kreirani."); st.rerun()
                except Exception as e: st.error(f"Greška: {e}")

    elif menu == "🛠️ Uređivanje Podataka":
        st.header("🛠️ Uređivanje Podataka")
        sel_e = st.selectbox("Djelatnik:", ["---"] + [f"{r['ime_prezime']} ({r['kadrovski_broj']})" for _, r in df_master.iterrows()])
        if sel_e != "---":
            eid = sel_e.split("(")[1].replace(")", "")
            curr = df_master[df_master['kadrovski_broj'] == eid].iloc[0]
            with st.form("admin_edit"):
                n_ime = st.text_input("Ime", value=curr['ime_prezime'])
                n_pw = st.text_input("Reset lozinke", type="password")
                if st.form_submit_button("Spremi"):
                    with sqlite3.connect(DB_FILE) as db:
                        db.execute("UPDATE employees_master SET ime_prezime=? WHERE kadrovski_broj=?", (n_ime, eid))
                        if n_pw: db.execute("UPDATE users SET password=? WHERE username=?", (get_hash(n_pw), eid))
                    st.success("Spremljeno!"); st.rerun()

    elif menu == "⚙️ Postavke Razdoblja":
        st.header("⚙️ Postavke Razdoblja")
        t1, t2, t3 = st.tabs(["Aktivacija", "Rokovi", "Brisanje"])
        with t1:
            # FIX: Zasebna konekcija za dohvat
            p_conn = get_connection()
            per_list = pd.read_sql_query("SELECT period_name FROM periods WHERE company_id=?", p_conn, params=(company_id,))
            p_conn.close()
            
            try: curr_idx = per_list['period_name'].tolist().index(current_period)
            except: curr_idx = 0
            
            s_p = st.selectbox("Aktivno razdoblje:", per_list['period_name'].tolist() if not per_list.empty else [], index=curr_idx)
            if st.button("Postavi kao Aktivno"):
                with sqlite3.connect(DB_FILE) as db:
                    db.execute("UPDATE app_settings SET setting_value=? WHERE setting_key='active_period'", (s_p,))
                    db.commit()
                st.success(f"Postavljeno: {s_p}"); time.sleep(0.5); st.rerun()
            
            st.divider()
            with st.form("np"):
                nn = st.text_input("Novi naziv (npr. 2026-Q2)"); nd = st.date_input("Rok")
                if st.form_submit_button("Kreiraj"):
                    if nn:
                        # FIX: Koristimo 'with' za sigurno spremanje i time.sleep
                        with sqlite3.connect(DB_FILE) as db:
                            db.execute("INSERT OR REPLACE INTO periods (period_name, deadline, company_id) VALUES (?,?,?)", (nn, str(nd), company_id))
                            db.execute("UPDATE app_settings SET setting_value=? WHERE setting_key='active_period'", (nn,))
                            db.commit()
                        st.success(f"Kreirano i aktivirano: {nn}"); time.sleep(0.5); st.rerun()
        with t2:
            st.write(f"Trenutni rok za {current_period}: {deadline}")
            nr = st.date_input("Novi rok")
            if st.button("Spremi rok"):
                with sqlite3.connect(DB_FILE) as db:
                    db.execute("UPDATE periods SET deadline=? WHERE period_name=?", (str(nr), current_period))
                    db.commit()
                st.success("Spremljeno!"); time.sleep(0.5); st.rerun()
        with t3:
            if not per_list.empty:
                dp = st.selectbox("Briši:", per_list['period_name'].tolist())
                if st.button("Obriši") and dp != current_period:
                    with sqlite3.connect(DB_FILE) as db:
                        db.execute("DELETE FROM periods WHERE period_name=?", (dp,))
                        db.commit()
                    st.success("Obrisano!"); time.sleep(0.5); st.rerun()

    elif menu == "📥 Export":
        st.header("📥 Export")
        if st.button("Excel"):
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                for t in ["employees_master", "evaluations", "users", "goals", "development_plans"]:
                    try: pd.read_sql_query(f"SELECT * FROM {t} WHERE company_id={company_id}", conn).to_excel(writer, sheet_name=t[:31], index=False)
                    except: pass
            st.download_button("Preuzmi", buffer.getvalue(), f"Export_{date.today()}.xlsx")

    conn.close()