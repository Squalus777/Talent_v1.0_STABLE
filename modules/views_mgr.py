import streamlit as st
import pandas as pd
import json
import io
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import time
from datetime import datetime, date
import streamlit.components.v1 as components

from modules.database import get_connection, get_active_period_info, DB_FILE, save_evaluation_json_method
from modules.utils import (
    calculate_category, render_metric_input, 
    table_to_json_string, get_df_from_json, get_active_survey_questions,
    safe_load_json, normalize_progress, create_9box_grid
)
from modules.constants import MAX_TITLE_LENGTH, MAX_TEXT_LENGTH
from modules.goals_cascade import render_team_goals_manager

def render_manager_view():
    conn = get_connection()
    current_period, deadline = get_active_period_info()
    username = st.session_state.get('username')
    company_id = st.session_state.get('company_id', 1)
    
    # INFO BAR
    st.info(f"📅 **AKTIVNO RAZDOBLJE:** {current_period}  |  ⏳ **ROK:** {deadline}")
    
    mode, survey_data = get_active_survey_questions(current_period, company_id)
    
    # IZBORNIK
    menu = st.sidebar.radio("Voditeljski Izbornik", [
        "📊 Dashboard", 
        "👤 Moji Rezultati",
        "🎯 Ciljevi Tima", 
        "📝 Unos Procjena", 
        "🚀 Razvojni Planovi (IDP)", 
        "🤝 Upravljanje Ljudima",
        "📥 Export Podataka"
    ])

    # ----------------------------------------------------------------
    # 1. DASHBOARD
    # ----------------------------------------------------------------
    if menu == "📊 Dashboard":
        st.header(f"📊 Moj Dashboard")
        my_team = pd.read_sql_query("SELECT * FROM employees_master WHERE manager_id=? AND company_id=?", conn, params=(username, company_id))
        
        # Statistika
        evals = pd.read_sql_query("SELECT * FROM evaluations WHERE period=? AND manager_id=? AND is_self_eval=0", conn, params=(current_period, username))
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Moj Tim", len(my_team))
        finished = len(evals[evals['status']=='Submitted'])
        c2.metric("Završeno", f"{finished} / {len(my_team)}")
        avg_score = evals['avg_performance'].mean() if not evals.empty else 0
        c3.metric("Prosjek Tima", f"{avg_score:.2f}")

        t1, t2 = st.tabs(["9-Box Matrica", "Povijest (Snail Trail)"])
        with t1:
            if not evals.empty:
                fig = create_9box_grid(evals, title="9-Box Matrica Tima")
                if fig: st.plotly_chart(fig, use_container_width=True)
            else: st.info("Nema podataka.")
        
        with t2:
            if not my_team.empty:
                sel = st.selectbox("Odaberi zaposlenika:", my_team['ime_prezime'].tolist())
                kid = my_team[my_team['ime_prezime']==sel]['kadrovski_broj'].values[0]
                hist = pd.read_sql_query("SELECT period, avg_performance, avg_potential FROM evaluations WHERE kadrovski_broj=? AND is_self_eval=0 AND status='Submitted' ORDER BY period", conn, params=(kid,))
                
                if not hist.empty:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=hist['avg_performance'], 
                        y=hist['avg_potential'],
                        mode='lines+markers+text',
                        text=hist['period'], 
                        textposition="top center",
                        marker=dict(size=12, color='blue'),
                        line=dict(color='rgba(0,0,255,0.3)', width=2, dash='dot'),
                        name='Razvojni put'
                    ))
                    
                    fig.update_layout(
                        title=f"Razvojni put: {sel}",
                        xaxis=dict(title="Učinak (Performance)", range=[0.5, 5.5], showgrid=False),
                        yaxis=dict(title="Potencijal (Potential)", range=[0.5, 5.5], showgrid=False),
                        shapes=[
                            dict(type="line", x0=2.5, x1=2.5, y0=0, y1=6, line=dict(color="gray", width=1, dash="dot")),
                            dict(type="line", x0=4.0, x1=4.0, y0=0, y1=6, line=dict(color="gray", width=1, dash="dot")),
                            dict(type="line", x0=0, x1=6, y0=2.5, y1=2.5, line=dict(color="gray", width=1, dash="dot")),
                            dict(type="line", x0=0, x1=6, y0=4.0, y1=4.0, line=dict(color="gray", width=1, dash="dot")),
                        ]
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else: st.info("Nema povijesnih podataka (službenih procjena).")

    # ----------------------------------------------------------------
    # 2. MOJI REZULTATI
    # ----------------------------------------------------------------
    elif menu == "👤 Moji Rezultati":
        st.header("👤 Moji Rezultati")
        me_eval = pd.read_sql_query("SELECT * FROM evaluations WHERE kadrovski_broj=? AND period=? AND is_self_eval=0", conn, params=(username, current_period))
        if not me_eval.empty:
            r = me_eval.iloc[0]
            st.info(f"Status: {r['status']}")
            c1, c2, c3 = st.columns(3)
            c1.metric("Učinak", f"{r['avg_performance']:.2f}")
            c2.metric("Potencijal", f"{r['avg_potential']:.2f}")
            c3.metric("Kategorija", r['category'])
            st.write("**Komentar nadređenog:**")
            st.write(r['action_plan'])
        else: st.warning("Vaša procjena još nije unesena.")

    # ----------------------------------------------------------------
    # 3. CILJEVI TIMA
    # ----------------------------------------------------------------
    elif menu == "🎯 Ciljevi Tima":
        render_team_goals_manager(username, company_id, current_period)

    # ----------------------------------------------------------------
    # 4. UNOS PROCJENA
    # ----------------------------------------------------------------
    elif menu == "📝 Unos Procjena":
        st.header("📝 Procjena Zaposlenika")
        my_team = pd.read_sql_query("SELECT * FROM employees_master WHERE manager_id=? AND company_id=?", conn, params=(username, company_id))
        
        for _, emp in my_team.iterrows():
            kid = emp['kadrovski_broj']
            r_df = pd.read_sql_query("SELECT * FROM evaluations WHERE kadrovski_broj=? AND period=? AND is_self_eval=0", conn, params=(kid, current_period))
            r = r_df.iloc[0] if not r_df.empty else None
            
            is_locked = (r is not None and str(r['status']).strip() == 'Submitted')
            status_icon = "🔒" if is_locked else "✏️"
            status_text = "Završeno" if is_locked else ("U tijeku" if r is not None else "Nije započeto")
            
            with st.expander(f"{status_icon} {emp['ime_prezime']} ({status_text})"):
                tab_input, tab_gap = st.tabs(["🖊️ Unos Ocjena", "🔍 Gap Analiza"])
                
                # --- TAB 1: UNOS OCJENA (ILI PREGLED ZAKLJUČANOG) ---
                with tab_input:
                    if is_locked:
                        st.success("✅ Procjena je zaključana i poslana.")
                        
                        # PRINT BUTTON
                        if st.button(f"🖨️ Pripremi za Ispis (PDF View)", key=f"print_{kid}"):
                            st.markdown("---")
                            st.markdown(f"## 📄 IZVJEŠTAJ O UČINKU: {current_period}")
                            st.markdown(f"**Zaposlenik:** {emp['ime_prezime']} | **Manager:** {username}")
                            st.markdown("---")
                            
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Učinak", f"{r['avg_performance']:.2f}")
                            c2.metric("Potencijal", f"{r['avg_potential']:.2f}")
                            c3.metric("Kategorija", r['category'])
                            
                            st.markdown("### Detaljne Ocjene")
                            saved = safe_load_json(r['json_answers'])
                            
                            st.markdown("#### Učinak")
                            for m in survey_data['p']:
                                val = saved.get(str(m['id']), "-")
                                st.write(f"**{m['title']}:** {val} / 5")
                            
                            st.markdown("#### Potencijal")
                            for m in survey_data['pot']:
                                val = saved.get(str(m['id']), "-")
                                st.write(f"**{m['title']}:** {val} / 5")
                            
                            st.markdown("### Zaključni Komentar i Akcijski Plan")
                            st.info(r['action_plan'])
                            st.caption("💡 Savjet: Za spremanje u PDF pritisnite Ctrl+P (Windows) ili Cmd+P (Mac) i odaberite 'Save as PDF'.")
                            st.markdown("---")
                        else:
                            # Standardni Read-Only prikaz (ako nije print mode)
                            c1, c2, c3 = st.columns(3)
                            c1.metric("Učinak", f"{r['avg_performance']:.2f}")
                            c2.metric("Potencijal", f"{r['avg_potential']:.2f}")
                            c3.metric("Kategorija", r['category'])
                            
                            st.markdown("---")
                            st.subheader("Detaljni pregled")
                            saved = safe_load_json(r['json_answers'])
                            
                            cr1, cr2 = st.columns(2)
                            with cr1:
                                st.markdown("**Učinak**")
                                for m in survey_data['p']:
                                    val = saved.get(str(m['id']), "-")
                                    st.write(f"- {m['title']}: **{val}**")
                            with cr2:
                                st.markdown("**Potencijal**")
                                for m in survey_data['pot']:
                                    val = saved.get(str(m['id']), "-")
                                    st.write(f"- {m['title']}: **{val}**")
                                    
                            st.write("**Vaš komentar:**")
                            st.text_area("Komentar", value=r['action_plan'], disabled=True, height=100)

                    else:
                        # FORMA ZA UNOS
                        with st.form(f"eval_form_{kid}"):
                            saved = safe_load_json(r['json_answers'] if r is not None else None)
                            scores_p = []
                            scores_pot = []
                            
                            c1, c2 = st.columns(2)
                            with c1:
                                st.subheader("Učinak")
                                for m in survey_data['p']:
                                    val = int(saved.get(str(m['id']), 3))
                                    s = render_metric_input(m['title'], m['def'], m['crit'], f"p_{kid}_{m['id']}", val, "perf")
                                    scores_p.append((str(m['id']), s))
                            with c2:
                                st.subheader("Potencijal")
                                for m in survey_data['pot']:
                                    val = int(saved.get(str(m['id']), 3))
                                    s = render_metric_input(m['title'], m['def'], m['crit'], f"pot_{kid}_{m['id']}", val, "pot")
                                    scores_pot.append((str(m['id']), s))

                            plan = st.text_area("Komentar / Akcijski plan", r['action_plan'] if r is not None else "", max_chars=MAX_TEXT_LENGTH)
                            
                            col_d, col_f = st.columns(2)
                            is_draft = col_d.form_submit_button("💾 Spremi kao Nacrt")
                            is_final = col_f.form_submit_button("✅ Pošalji i Zaključaj")
                            
                            if is_draft or is_final:
                                vals_p = [x[1] for x in scores_p]
                                vals_pot = [x[1] for x in scores_pot]
                                avg_p = sum(vals_p) / len(vals_p) if vals_p else 0
                                avg_pot = sum(vals_pot) / len(vals_pot) if vals_pot else 0
                                cat = calculate_category(avg_p, avg_pot)
                                
                                all_ans = {**dict(scores_p), **dict(scores_pot)}
                                user_data = {'ime': emp['ime_prezime'], 'radno_mjesto': emp['radno_mjesto'], 'odjel': emp['department']}
                                status = "Submitted" if is_final else "Draft"
                                
                                success, msg = save_evaluation_json_method(company_id, current_period, kid, username, user_data, vals_p, vals_pot, avg_p, avg_pot, cat, plan, all_ans, False, status)
                                if success:
                                    if is_final: st.balloons()
                                    st.success("Spremljeno!")
                                    time.sleep(1)
                                    st.rerun()
                                else: st.error(msg)

                # --- TAB 2: GAP ANALIZA (PUNI KOD) ---
                with tab_gap:
                    se_df = pd.read_sql_query("SELECT * FROM evaluations WHERE kadrovski_broj=? AND period=? AND is_self_eval=1", conn, params=(kid, current_period))
                    if not se_df.empty:
                        se_row = se_df.iloc[0]
                        
                        # Učitaj JSON odgovore
                        mgr_json = safe_load_json(r['json_answers'] if r is not None else None)
                        se_json = safe_load_json(se_row['json_answers'])
                        
                        gap_data = []
                        all_questions = survey_data['p'] + survey_data['pot']
                        
                        for q in all_questions:
                            qid = str(q['id'])
                            try:
                                s_mgr = int(mgr_json.get(qid, 0))
                                s_emp = int(se_json.get(qid, 0))
                            except:
                                s_mgr, s_emp = 0, 0
                                
                            diff = s_mgr - s_emp
                            
                            gap_data.append({
                                "Kategorija": "Učinak" if q in survey_data['p'] else "Potencijal",
                                "Pitanje": q['title'],
                                "Radnik": s_emp,
                                "Manager": s_mgr,
                                "Razlika": diff
                            })
                        
                        gap_df = pd.DataFrame(gap_data)
                        
                        # Prikaz metrike
                        c1, c2 = st.columns(2)
                        c1.metric("Samoprocjena (Prosjek)", f"{se_row['avg_performance']:.2f}")
                        if r is not None:
                            c2.metric("Vaša ocjena (Prosjek)", f"{r['avg_performance']:.2f}")
                        
                        st.write("#### Detaljna usporedba")
                        # Jednostavan color highlight za dataframe
                        st.dataframe(gap_df.style.applymap(lambda x: 'color: red' if x < 0 else ('color: green' if x > 0 else 'color: gray'), subset=['Razlika']), use_container_width=True)
                        
                    else:
                        st.warning("Radnik još nije ispunio samoprocjenu, pa usporedba nije moguća.")

    # ----------------------------------------------------------------
    # 5. IDP (RAZVOJNI PLANOVI)
    # ----------------------------------------------------------------
    elif menu == "🚀 Razvojni Planovi (IDP)":
        st.header("🚀 Razvojni Planovi (IDP)")
        team = pd.read_sql_query("SELECT * FROM employees_master WHERE manager_id=?", conn, params=(username,))
        
        if not team.empty:
            for _, emp in team.iterrows():
                eid = emp['kadrovski_broj']
                res = conn.execute("SELECT * FROM development_plans WHERE kadrovski_broj=? AND period=?", (eid, current_period)).fetchone()
                d = dict(zip([c[1] for c in conn.execute("PRAGMA table_info(development_plans)").fetchall()], res)) if res else {}
                
                status_icon = "🟢" if d.get('status') == 'Active' else "⚪"
                
                with st.expander(f"{status_icon} {emp['ime_prezime']} ({emp['radno_mjesto']})"):
                    with st.form(f"idp_form_{eid}"):
                        st.subheader("1. Dijagnoza i Smjer")
                        c1, c2 = st.columns(2)
                        with c1: val_s = st.text_area("💪 Ključne Snage", value=d.get('strengths',''), height=100, max_chars=MAX_TEXT_LENGTH, help="U čemu je zaposlenik izniman?")
                        with c2: val_w = st.text_area("🚧 Područja za razvoj", value=d.get('areas_improve',''), height=100, max_chars=MAX_TEXT_LENGTH, help="Što koči zaposlenika?")
                        val_g = st.text_input("🎯 Karijerni cilj", value=d.get('career_goal',''), max_chars=MAX_TITLE_LENGTH, help="Kratkoročni ili dugoročni cilj?")
                        
                        st.markdown("---")
                        st.subheader("2. Akcijski plan (Max 15 redaka po tablici)")
                        
                        # --- 70% ISKUSTVO ---
                        st.info("📌 **70% - Učenje kroz rad (Iskustvo)**\n\nNovi zadaci, projekti, rotacije, povećanje odgovornosti.")
                        d70 = st.data_editor(get_df_from_json(d.get('json_70',''), ["Što razviti?", "Aktivnost", "Rok", "Dokaz"]), key=f"d70_{eid}", num_rows="dynamic", use_container_width=True)
                        
                        # --- 20% MENTORING ---
                        st.info("👥 **20% - Učenje od drugih (Izloženost)**\n\nMentoring, coaching, feedback, shadowing, networking.")
                        d20 = st.data_editor(get_df_from_json(d.get('json_20',''), ["Što razviti?", "Aktivnost", "Rok"]), key=f"d20_{eid}", num_rows="dynamic", use_container_width=True)
                        
                        # --- 10% EDUKACIJA ---
                        st.info("📚 **10% - Formalna edukacija**\n\nTečajevi, certifikati, knjige, konferencije.")
                        d10 = st.data_editor(get_df_from_json(d.get('json_10',''), ["Edukacija", "Trošak", "Rok"]), key=f"d10_{eid}", num_rows="dynamic", use_container_width=True)
                        
                        st.markdown("---")
                        st.subheader("3. Podrška")
                        curr_supp = d.get('support_needed', '---')
                        supp_opts = ["---", "Mentoring", "Coaching", "Budžet", "Slobodni dani", "Rotacija posla", "Tehnička oprema"]
                        if curr_supp not in supp_opts: curr_supp = "---"
                        new_supp = st.selectbox("Vrsta podrške:", supp_opts, index=supp_opts.index(curr_supp), key=f"supp_{eid}")
                        new_notes = st.text_area("Napomene:", value=d.get('support_notes',''), max_chars=MAX_TEXT_LENGTH, key=f"notes_{eid}")

                        if st.form_submit_button("💾 Spremi Razvojni Plan"):
                            # VALIDACIJA LIMITA REDAKA
                            if len(d70) > 15 or len(d20) > 15 or len(d10) > 15:
                                st.error("❌ Previše redaka! Maksimalno 15 aktivnosti po tablici.")
                            else:
                                with sqlite3.connect(DB_FILE) as db:
                                    db.execute("DELETE FROM development_plans WHERE kadrovski_broj=? AND period=?", (eid, current_period))
                                    db.execute("""INSERT INTO development_plans (period, kadrovski_broj, manager_id, strengths, areas_improve, career_goal, json_70, json_20, json_10, support_needed, support_notes, status, company_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                               (current_period, eid, username, val_s, val_w, val_g, table_to_json_string(d70), table_to_json_string(d20), table_to_json_string(d10), new_supp, new_notes, 'Active', company_id))
                                st.success("IDP Spremljen!"); time.sleep(1); st.rerun()
        else: st.info("Nemate dodijeljenih članova tima.")

    # ----------------------------------------------------------------
    # 6. UPRAVLJANJE LJUDIMA
    # ----------------------------------------------------------------
    elif menu == "🤝 Upravljanje Ljudima":
        st.header("🤝 Upravljanje Ljudima")
        my_team = pd.read_sql_query("SELECT * FROM employees_master WHERE manager_id=?", conn, params=(username,))
        t1, t2 = st.tabs(["Pohvale", "Delegiranje"])
        with t1:
            with st.form("mgr_kudos"):
                rec = st.selectbox("Zaposlenik:", my_team['ime_prezime'].tolist())
                msg = st.text_area("Poruka:", max_chars=MAX_TEXT_LENGTH)
                if st.form_submit_button("Pošalji"):
                    rid = my_team[my_team['ime_prezime']==rec]['kadrovski_broj'].values[0]
                    conn.execute("INSERT INTO recognitions (sender_id, receiver_id, message, timestamp, company_id) VALUES (?,?,?,?,?)", (username, rid, msg, str(date.today()), company_id))
                    conn.commit(); st.success("Poslano!")
        with t2: st.info("Delegiranje zadataka (Coming soon).")

    # ----------------------------------------------------------------
    # 7. EXPORT PODATAKA
    # ----------------------------------------------------------------
    elif menu == "📥 Export Podataka":
        st.header("📥 Export Mojih Podataka")
        st.caption("Preuzmite podatke vašeg tima u Excel formatu.")
        
        if st.button("Preuzmi Excel (Moj Tim)"):
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                pd.read_sql_query("SELECT * FROM employees_master WHERE manager_id=?", conn, params=(username,)).to_excel(writer, sheet_name="Moj Tim")
                pd.read_sql_query("SELECT * FROM evaluations WHERE manager_id=? AND period=? AND status='Submitted'", conn, params=(username, current_period)).to_excel(writer, sheet_name="Procjene")
                pd.read_sql_query("SELECT * FROM goals WHERE manager_id=? AND period=?", conn, params=(username, current_period)).to_excel(writer, sheet_name="Ciljevi")
            st.download_button("Download Excel", buffer.getvalue(), f"export_team_{username}_{date.today()}.xlsx")

    conn.close()