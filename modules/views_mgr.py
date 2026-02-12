import streamlit as st
import pandas as pd
import json
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import time
from datetime import datetime, date
import streamlit.components.v1 as components

from modules.database import get_connection, get_active_period_info, DB_FILE, save_evaluation_json_method
# 1. IMPORT NOVIH SIGURNIH FUNKCIJA (JEDINA PROMJENA NA VRHU)
from modules.utils import (
    calculate_category, render_metric_input, 
    table_to_json_string, get_df_from_json, get_active_survey_questions,
    safe_load_json, normalize_progress, create_9box_grid
)

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
        "🤝 Upravljanje Ljudima"
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
                # 2. PROMJENA: Korištenje centralizirane funkcije umjesto ručnog px.scatter
                fig = create_9box_grid(evals, title="9-Box Matrica Tima")
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
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
        st.header("🎯 Ciljevi Tima")
        my_team = pd.read_sql_query("SELECT * FROM employees_master WHERE manager_id=?", conn, params=(username,))
        
        with st.expander("➕ Dodaj Novi Cilj", expanded=False):
            with st.form("new_goal"):
                emp = st.selectbox("Zaposlenik:", my_team['ime_prezime'].tolist())
                tit = st.text_input("Naziv cilja")
                wei = st.number_input("Težina cilja (%)", 1, 100, 25, help="Koliko ovaj cilj nosi u ukupnoj ocjeni zaposlenika?")
                desc = st.text_area("Opis / KPI")
                dline = st.date_input("Rok")
                if st.form_submit_button("Kreiraj"):
                    kid = my_team[my_team['ime_prezime']==emp]['kadrovski_broj'].values[0]
                    conn.execute("INSERT INTO goals (period, kadrovski_broj, manager_id, title, description, weight, progress, status, last_updated, deadline, company_id) VALUES (?,?,?,?,?,?,0,'On Track',?,?,?)",
                               (current_period, kid, username, tit, desc, wei, datetime.now().strftime("%Y-%m-%d"), str(dline), company_id))
                    conn.commit()
                    st.success("Dodano!")
                    st.rerun()

        for _, emp in my_team.iterrows():
            eid = emp['kadrovski_broj']
            goals = pd.read_sql_query("SELECT * FROM goals WHERE kadrovski_broj=? AND period=?", conn, params=(eid, current_period))
            tot_w = goals['weight'].sum() if not goals.empty else 0
            
            color = "green" if tot_w == 100 else "red"
            with st.expander(f"👤 {emp['ime_prezime']} (Ukupna težina ciljeva: :{color}[{tot_w}%])"):
                if tot_w != 100: st.warning(f"⚠️ Zbroj težina svih ciljeva mora biti točno 100%! Trenutno: {tot_w}%")
                
                for _, g in goals.iterrows():
                    gid = g['id']
                    
                    c_title, c_act = st.columns([4, 1])
                    c_title.markdown(f"### 🎯 {g['title']} ({g['weight']}%)")
                    
                    if c_act.button("🗑️ Briši", key=f"pre_del_{gid}"):
                        st.session_state[f"confirm_del_{gid}"] = True
                    
                    if st.session_state.get(f"confirm_del_{gid}"):
                        st.error("Jeste li sigurni? Ovo briše cilj i sve njegove KPI-eve.")
                        col_yes, col_no = st.columns(2)
                        if col_yes.button("DA, Obriši", key=f"yes_del_{gid}"):
                            conn.execute("DELETE FROM goals WHERE id=?", (gid,))
                            conn.execute("DELETE FROM goal_kpis WHERE goal_id=?", (gid,))
                            conn.commit()
                            st.rerun()
                        if col_no.button("Odustani", key=f"no_del_{gid}"):
                            st.session_state[f"confirm_del_{gid}"] = False
                            st.rerun()

                    with st.expander("✏️ Uredi detalje cilja"):
                        with st.form(f"edit_goal_{gid}"):
                            nt = st.text_input("Naziv", g['title'])
                            nw = st.number_input("Težina (%)", 1, 100, g['weight'])
                            nd = st.text_area("Opis", g['description'])
                            if st.form_submit_button("Ažuriraj Cilj"):
                                conn.execute("UPDATE goals SET title=?, weight=?, description=? WHERE id=?", (nt, nw, nd, gid))
                                conn.commit()
                                st.success("Ažurirano!")
                                st.rerun()

                    st.write("**Ključni pokazatelji (KPI) unutar ovog cilja:**")
                    kpis = pd.read_sql_query("SELECT description, weight, progress FROM goal_kpis WHERE goal_id=?", conn, params=(gid,))
                    
                    df_k = kpis.rename(columns={'description':'KPI Naziv','weight':'Težina (%)','progress':'Ostvarenje (%)'}) if not kpis.empty else pd.DataFrame(columns=['KPI Naziv','Težina (%)','Ostvarenje (%)'])
                    
                    ed = st.data_editor(df_k, key=f"k_{gid}", num_rows="dynamic", use_container_width=True)
                    
                    if st.button("💾 Spremi KPI i Izračunaj", key=f"s_{gid}"):
                        ed['Težina (%)'] = pd.to_numeric(ed['Težina (%)'], errors='coerce').fillna(0)
                        ed['Ostvarenje (%)'] = pd.to_numeric(ed['Ostvarenje (%)'], errors='coerce').fillna(0)
                        
                        current_kpi_sum = ed['Težina (%)'].sum()
                        
                        conn.execute("DELETE FROM goal_kpis WHERE goal_id=?", (gid,))
                        weighted_progress_sum = 0
                        
                        for _, r in ed.iterrows():
                            if str(r['KPI Naziv']).strip():
                                w_val = float(r['Težina (%)'])
                                p_val = float(r['Ostvarenje (%)'])
                                conn.execute("INSERT INTO goal_kpis (goal_id, description, weight, progress) VALUES (?,?,?,?)", (gid, str(r['KPI Naziv']), w_val, p_val))
                                weighted_progress_sum += (w_val * p_val) / 100
                        
                        conn.execute("UPDATE goals SET progress=?, last_updated=? WHERE id=?", (weighted_progress_sum, datetime.now().strftime("%Y-%m-%d"), gid))
                        conn.commit()
                        
                        if current_kpi_sum != 100:
                            st.warning(f"⚠️ KPI-evi su spremljeni, ali zbroj težina je {current_kpi_sum}% (cilj je 100%).")
                        else:
                            st.success(f"✅ Spremljeno! Napredak cilja: {weighted_progress_sum:.1f}%")
                        
                        time.sleep(1)
                        st.rerun()
                    
                    # 3. PROMJENA: Dodan normalize_progress u st.progress
                    st.progress(normalize_progress(g['progress']))
                    st.caption(f"Ostvarenje cilja: {g['progress']:.1f}%")
                    st.divider()

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
                tab_input, tab_gap = st.tabs(["🖊️ Unos Ocjena", "🔍 Gap Analiza (Usporedba)"])
                
                with tab_input:
                    if is_locked:
                        st.success("✅ Ova procjena je zaključana i poslana.")
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Učinak", f"{r['avg_performance']:.2f}")
                        c2.metric("Potencijal", f"{r['avg_potential']:.2f}")
                        c3.metric("Kategorija", r['category'])
                        
                        st.markdown("---")
                        st.markdown("### 📋 Detaljni prikaz ocjena (Read-Only)")
                        
                        saved = {}
                        if r['json_answers']:
                            try: saved = json.loads(r['json_answers'])
                            except: pass
                        
                        cr1, cr2 = st.columns(2)
                        with cr1:
                            st.markdown("#### Učinak")
                            for m in survey_data['p']:
                                val = saved.get(str(m['id']), "-")
                                st.markdown(f"**{m['title']}**: :blue[{val}]")
                                st.caption(f"_{m['def']}_")
                                st.divider()
                        with cr2:
                            st.markdown("#### Potencijal")
                            for m in survey_data['pot']:
                                val = saved.get(str(m['id']), "-")
                                st.markdown(f"**{m['title']}**: :blue[{val}]")
                                st.caption(f"_{m['def']}_")
                                st.divider()

                        st.write("**Zaključni komentar:**")
                        st.info(r['action_plan'])
                    else:
                        with st.form(f"eval_form_{kid}"):
                            # 4. PROMJENA: safe_load_json umjesto čistog json.loads
                            saved = safe_load_json(r['json_answers'] if r is not None else None)
                            
                            scores_p = []
                            scores_pot = []
                            
                            c1, c2 = st.columns(2)
                            with c1:
                                st.subheader("Učinak (Performance)")
                                for m in survey_data['p']:
                                    key_p = f"p_{kid}_{m['id']}"
                                    val = int(saved.get(str(m['id']), 3))
                                    s = render_metric_input(m['title'], m['def'], m['crit'], key_p, val, "perf")
                                    scores_p.append((str(m['id']), s))
                                    
                            with c2:
                                st.subheader("Potencijal (Potential)")
                                for m in survey_data['pot']:
                                    key_pot = f"pot_{kid}_{m['id']}"
                                    val = int(saved.get(str(m['id']), 3))
                                    s = render_metric_input(m['title'], m['def'], m['crit'], key_pot, val, "pot")
                                    scores_pot.append((str(m['id']), s))

                            plan = st.text_area("Komentar / Akcijski plan", r['action_plan'] if r is not None else "")
                            
                            col_draft, col_final = st.columns(2)
                            is_draft = col_draft.form_submit_button("💾 Spremi kao Nacrt")
                            is_final = col_final.form_submit_button("✅ Pošalji i Zaključaj")
                            
                            if is_draft or is_final:
                                vals_p = [x[1] for x in scores_p]
                                vals_pot = [x[1] for x in scores_pot]
                                avg_p = sum(vals_p) / len(vals_p) if vals_p else 0
                                avg_pot = sum(vals_pot) / len(vals_pot) if vals_pot else 0
                                cat = calculate_category(avg_p, avg_pot)
                                
                                all_answers = {}
                                for pid, pval in scores_p: all_answers[pid] = pval
                                for potid, potval in scores_pot: all_answers[potid] = potval
                                
                                user_data = {'ime': emp['ime_prezime'], 'radno_mjesto': emp['radno_mjesto'], 'odjel': emp['department']}
                                target_status = "Submitted" if is_final else "Draft"
                                
                                success, msg = save_evaluation_json_method(
                                    company_id, current_period, kid, username, user_data, 
                                    vals_p, vals_pot, avg_p, avg_pot, cat, plan, 
                                    all_answers, False, target_status
                                )
                                
                                if success:
                                    if is_final: st.balloons()
                                    st.success(f"Procjena {target_status}!")
                                    time.sleep(1)
                                    st.rerun()
                                else: st.error(msg)

                with tab_gap:
                    se_df = pd.read_sql_query("SELECT * FROM evaluations WHERE kadrovski_broj=? AND period=? AND is_self_eval=1", conn, params=(kid, current_period))
                    if not se_df.empty:
                        se_row = se_df.iloc[0]
                        # 4. PROMJENA: safe_load_json i ovdje
                        mgr_json = safe_load_json(r['json_answers'] if r is not None else None)
                        se_json = safe_load_json(se_row['json_answers'])
                        
                        gap_data = []
                        for q in survey_data['p'] + survey_data['pot']:
                            qid = str(q['id'])
                            s_mgr = int(mgr_json.get(qid, 0))
                            s_emp = int(se_json.get(qid, 0))
                            gap_data.append({"Pitanje": q['title'], "Radnik": s_emp, "Manager": s_mgr, "Razlika": s_mgr - s_emp})
                        st.table(pd.DataFrame(gap_data))
                    else: st.warning("Radnik još nije ispunio samoprocjenu.")

    # ----------------------------------------------------------------
    # 5. IDP (RAZVOJNI PLANOVI) - EXPANDERI + BOGATI SADRŽAJ
    # ----------------------------------------------------------------
    elif menu == "🚀 Razvojni Planovi (IDP)":
        st.header("🚀 Razvojni Planovi (IDP)")
        team = pd.read_sql_query("SELECT * FROM employees_master WHERE manager_id=?", conn, params=(username,))
        
        if not team.empty:
            for _, emp in team.iterrows():
                eid = emp['kadrovski_broj']
                
                # Dohvat podataka za ovog radnika
                res = conn.execute("SELECT * FROM development_plans WHERE kadrovski_broj=? AND period=?", (eid, current_period)).fetchone()
                d = {}
                if res:
                    cols = [c[1] for c in conn.execute("PRAGMA table_info(development_plans)").fetchall()]
                    d = dict(zip(cols, res))
                
                # Ikonica ovisno o statusu
                status_icon = "🟢" if d.get('status') == 'Active' else "⚪"
                
                # Expander po zaposleniku
                with st.expander(f"{status_icon} {emp['ime_prezime']} ({emp['radno_mjesto']})"):
                    with st.form(f"idp_form_{eid}"):
                        st.subheader("1. Dijagnoza i Smjer")
                        c1, c2 = st.columns(2)
                        with c1:
                            st.text_area("💪 Ključne Snage", value=d.get('strengths',''), height=100, help="U čemu je zaposlenik izniman?", key=f"s_{eid}")
                        with c2:
                            st.text_area("🚧 Područja za razvoj", value=d.get('areas_improve',''), height=100, help="Što koči zaposlenika ili što mu nedostaje?", key=f"w_{eid}")
                        
                        st.text_input("🎯 Karijerni cilj (kratkoročni/dugoročni)", value=d.get('career_goal',''), help="Koju poziciju ili razinu stručnosti ciljamo?", key=f"g_{eid}")
                        
                        st.markdown("---")
                        st.subheader("2. Akcijski plan (70-20-10 Model)")
                        
                        st.info("📌 **70% - Učenje kroz rad (Iskustvo)**\n\nNovi zadaci, projekti, rotacije, povećanje odgovornosti.")
                        d70 = st.data_editor(get_df_from_json(d.get('json_70',''), ["Što razviti?", "Aktivnost", "Rok", "Dokaz"]), key=f"d70_{eid}", num_rows="dynamic", use_container_width=True)
                        
                        st.info("👥 **20% - Učenje od drugih (Izloženost)**\n\nMentoring, coaching, feedback, shadowing, networking.")
                        d20 = st.data_editor(get_df_from_json(d.get('json_20',''), ["Što razviti?", "Aktivnost", "Rok"]), key=f"d20_{eid}", num_rows="dynamic", use_container_width=True)
                        
                        st.info("📚 **10% - Formalna edukacija**\n\nTečajevi, certifikati, knjige, konferencije.")
                        d10 = st.data_editor(get_df_from_json(d.get('json_10',''), ["Edukacija", "Trošak", "Rok"]), key=f"d10_{eid}", num_rows="dynamic", use_container_width=True)
                        
                        st.markdown("---")
                        st.subheader("3. Podrška i Resursi")
                        
                        sc1, sc2 = st.columns(2)
                        with sc1:
                            supp_opts = ["---", "Mentoring (Interni)", "Coaching (Vanjski)", "Budžet za edukaciju", "Slobodni dani za učenje", "Rotacija posla", "Tehnička oprema"]
                            curr_supp = d.get('support_needed', '---')
                            if curr_supp not in supp_opts: curr_supp = "---"
                            new_supp = st.selectbox("Primarna vrsta podrške:", supp_opts, index=supp_opts.index(curr_supp), key=f"supp_{eid}")
                        
                        with sc2:
                            new_notes = st.text_area("Dodatne napomene / Detalji podrške:", value=d.get('support_notes',''), key=f"notes_{eid}")

                        st.markdown("---")
                        if st.form_submit_button("💾 Spremi Razvojni Plan"):
                            with sqlite3.connect(DB_FILE) as db:
                                db.execute("DELETE FROM development_plans WHERE kadrovski_broj=? AND period=?", (eid, current_period))
                                db.execute("""INSERT INTO development_plans 
                                           (period, kadrovski_broj, manager_id, strengths, areas_improve, career_goal, 
                                           json_70, json_20, json_10, support_needed, support_notes, status, company_id) 
                                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                           (current_period, eid, username, d.get('strengths',''), d.get('areas_improve',''), d.get('career_goal',''), 
                                            table_to_json_string(d70), table_to_json_string(d20), table_to_json_string(d10), 
                                            new_supp, new_notes, 'Active', company_id))
                            st.toast(f"IDP za {emp['ime_prezime']} spremljen!", icon="✅")
                            time.sleep(1)
                            st.rerun()
        else:
            st.info("Nemate dodijeljenih članova tima.")

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
                msg = st.text_area("Poruka:")
                if st.form_submit_button("Pošalji"):
                    rid = my_team[my_team['ime_prezime']==rec]['kadrovski_broj'].values[0]
                    conn.execute("INSERT INTO recognitions (sender_id, receiver_id, message, timestamp, company_id) VALUES (?,?,?,?,?)", (username, rid, msg, str(date.today()), company_id))
                    conn.commit()
                    st.success("Poslano!")

        with t2:
            st.info("Ovdje možete delegirati procjene drugim voditeljima.")

    conn.close()