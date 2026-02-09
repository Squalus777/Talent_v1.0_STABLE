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
from modules.utils import (
    calculate_category, render_metric_input, 
    table_to_json_string, get_df_from_json, get_active_survey_questions
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
                fig = px.scatter(evals, x="avg_performance", y="avg_potential", color="category", text="ime_prezime", 
                                 range_x=[0.5,5.5], range_y=[0.5,5.5], title="9-Box Matrica (Trenutni period)")
                fig.add_vline(x=2.5, line_dash="dot", line_color="gray"); fig.add_vline(x=4.0, line_dash="dot", line_color="gray")
                fig.add_hline(y=2.5, line_dash="dot", line_color="gray"); fig.add_hline(y=4.0, line_dash="dot", line_color="gray")
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("Nema podataka.")
        
        # --- SNAIL TRAIL (KRETANJE KROZ MATRICU) ---
        with t2:
            if not my_team.empty:
                sel = st.selectbox("Odaberi zaposlenika:", my_team['ime_prezime'].tolist())
                kid = my_team[my_team['ime_prezime']==sel]['kadrovski_broj'].values[0]
                hist = pd.read_sql_query("SELECT period, avg_performance, avg_potential FROM evaluations WHERE kadrovski_broj=? AND is_self_eval=0 ORDER BY period", conn, params=(kid,))
                
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
    # 2. MOJI REZULTATI (Manager kao zaposlenik)
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
            st.write("**Komentar nadređenog:**"); st.write(r['action_plan'])
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
                    conn.commit(); st.success("Dodano!"); st.rerun()

        for _, emp in my_team.iterrows():
            eid = emp['kadrovski_broj']
            goals = pd.read_sql_query("SELECT * FROM goals WHERE kadrovski_broj=? AND period=?", conn, params=(eid, current_period))
            tot_w = goals['weight'].sum() if not goals.empty else 0
            
            color = "green" if tot_w == 100 else "red"
            with st.expander(f"👤 {emp['ime_prezime']} (Ukupna težina ciljeva: :{color}[{tot_w}%])"):
                if tot_w != 100: st.warning("⚠️ Zbroj težina svih ciljeva mora biti točno 100%!")
                
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
                                conn.commit(); st.success("Ažurirano!"); st.rerun()

                    st.write("**Ključni pokazatelji (KPI) unutar ovog cilja:**")
                    kpis = pd.read_sql_query("SELECT description, weight, progress FROM goal_kpis WHERE goal_id=?", conn, params=(gid,))
                    
                    df_k = kpis.rename(columns={'description':'KPI Naziv','weight':'Težina (%)','progress':'Ostvarenje (%)'}) if not kpis.empty else pd.DataFrame(columns=['KPI Naziv','Težina (%)','Ostvarenje (%)'])
                    
                    ed = st.data_editor(df_k, key=f"k_{gid}", num_rows="dynamic", use_container_width=True)
                    
                    if st.button("💾 Spremi KPI i Izračunaj", key=f"s_{gid}"):
                        current_kpi_sum = pd.to_numeric(ed['Težina (%)'], errors='coerce').fillna(0).sum()
                        
                        if current_kpi_sum != 100:
                            st.error(f"❌ Greška: Zbroj težina KPI-eva je {current_kpi_sum}%. Mora biti točno 100%!")
                        else:
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
                            st.success(f"✅ Spremljeno! Napredak cilja je sada: {weighted_progress_sum:.1f}%")
                            time.sleep(1); st.rerun()
                    
                    st.progress(float(g['progress'])/100)
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
                        
                        if st.button("🖨️ Prikaži PDF Preview", key=f"pdf_{kid}"):
                            html = f"""
                            <div style="border:2px solid #ccc; padding:20px; font-family:Arial;">
                                <h2>Izvještaj o učinku</h2>
                                <p><b>Zaposlenik:</b> {emp['ime_prezime']}</p>
                                <p><b>Period:</b> {current_period}</p>
                                <hr>
                                <h3>Rezultati</h3>
                                <p>Učinak: {r['avg_performance']:.2f}</p>
                                <p>Potencijal: {r['avg_potential']:.2f}</p>
                                <p><b>Kategorija: {r['category']}</b></p>
                                <hr>
                                <p><i>Dokument generiran sustavom Talent App</i></p>
                            </div>
                            """
                            components.html(html, height=400, scrolling=True)
                    else:
                        with st.form(f"eval_form_{kid}"):
                            saved = {}
                            if r is not None and r['json_answers']:
                                try: saved = json.loads(r['json_answers'])
                                except: pass
                            
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
                                
                                conn.close() 
                                success, msg = save_evaluation_json_method(
                                    company_id, current_period, kid, username, user_data, 
                                    vals_p, vals_pot, avg_p, avg_pot, cat, plan, 
                                    all_answers, False, target_status
                                )
                                
                                if success:
                                    if is_final:
                                        st.balloons()
                                        st.success("Procjena je uspješno poslana i zaključana!")
                                    else:
                                        st.toast("Nacrt uspješno spremljen!", icon="💾")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"Greška pri spremanju: {msg}")

                with tab_gap:
                    se_df = pd.read_sql_query("SELECT * FROM evaluations WHERE kadrovski_broj=? AND period=? AND is_self_eval=1", conn, params=(kid, current_period))
                    
                    if not se_df.empty:
                        se_row = se_df.iloc[0]
                        mgr_json = {}
                        if r is not None and r['json_answers']:
                            try: mgr_json = json.loads(r['json_answers'])
                            except: pass
                        se_json = {}
                        try: se_json = json.loads(se_row['json_answers'])
                        except: pass
                        
                        gap_data = []
                        all_qs = survey_data['p'] + survey_data['pot']
                        
                        for q in all_qs:
                            qid = str(q['id'])
                            s_mgr = int(mgr_json.get(qid, 0))
                            s_emp = int(se_json.get(qid, 0))
                            diff = s_mgr - s_emp
                            if diff == 0: status = "✅ Isto"
                            elif diff > 0: status = "📈 Više"
                            else: status = "📉 Niže"
                            
                            gap_data.append({
                                "Pitanje": q['title'],
                                "Zaposlenik": s_emp,
                                "Voditelj": s_mgr,
                                "Razlika": diff,
                                "Status": status
                            })
                        
                        df_gap = pd.DataFrame(gap_data)
                        
                        c1, c2 = st.columns(2)
                        c1.metric("Zaposlenik (Samoprocjena)", f"{se_row['avg_performance']:.2f} / {se_row['avg_potential']:.2f}")
                        if r is not None:
                            c2.metric("Voditelj (Trenutno)", f"{r['avg_performance']:.2f} / {r['avg_potential']:.2f}")
                        else: c2.info("Unesite ocjene da vidite usporedbu.")
                            
                        st.dataframe(df_gap.style.applymap(lambda x: 'background-color: #ffcccc' if x < 0 else ('background-color: #ccffcc' if x > 0 else ''), subset=['Razlika']), use_container_width=True)
                    else:
                        st.warning("Zaposlenik još nije ispunio samoprocjenu.")

    # ----------------------------------------------------------------
    # 5. IDP
    # ----------------------------------------------------------------
    elif menu == "🚀 Razvojni Planovi (IDP)":
        st.header("🚀 Razvojni Planovi (IDP)")
        team = pd.read_sql_query("SELECT * FROM employees_master WHERE manager_id=?", conn, params=(username,))
        for _, emp in team.iterrows():
            eid = emp['kadrovski_broj']
            res = conn.execute("SELECT * FROM development_plans WHERE kadrovski_broj=? AND period=?", (eid, current_period)).fetchone()
            d = dict(zip([c[1] for c in conn.execute("PRAGMA table_info(development_plans)").fetchall()], res)) if res else {}
            
            with st.expander(f"📄 {emp['ime_prezime']}"):
                st.markdown("### 1. DIJAGNOZA")
                s = st.text_area("Ključne snage (Što zadržati?)", d.get('strengths',''), key=f"s_{eid}")
                w = st.text_area("Područja za razvoj (Što popraviti?)", d.get('areas_improve',''), key=f"w_{eid}")
                g = st.text_input("Karijerni cilj (1-2 godine)", d.get('career_goal',''), key=f"g_{eid}")
                
                st.markdown("### 2. PLAN AKTIVNOSTI (70-20-10)")
                
                st.write("**A) 70% ISKUSTVO I PRAKSA (Rad na zadacima)**")
                st.caption("Učenje kroz rad – novi zadaci, projekti, rotacije poslova.")
                st.info("💡 **Primjer:** 'Preuzeti potpunu organizaciju jednog internog događaja od plana do realizacije.'")
                d70 = st.data_editor(
                    get_df_from_json(d.get('json_70',''), ["Što razviti?", "Aktivnost", "Rok", "Dokaz"]), 
                    key=f"d70_{eid}", num_rows="dynamic", use_container_width=True
                )
                
                st.write("**B) 20% UČENJE OD DRUGIH (Feedback & Mentoring)**")
                st.caption("Mentoring, coaching, shadowing, povratne informacije.")
                st.info("💡 **Primjer:** 'Kratki 1-na-1 sastanak s Voditeljem projekata jednom mjesečno radi feedbacka.'")
                d20 = st.data_editor(
                    get_df_from_json(d.get('json_20',''), ["Što razviti?", "Aktivnost", "Rok"]), 
                    key=f"d20_{eid}", num_rows="dynamic", use_container_width=True
                )
                
                st.write("**C) 10% FORMALNA EDUKACIJA (Tečajevi)**")
                st.caption("Trening, knjige, seminari, online tečajevi.")
                st.info("💡 **Primjer:** 'Završiti Excel Advanced tečaj na Udemy platformi.'")
                
                d10 = st.data_editor(
                    get_df_from_json(d.get('json_10',''), ["Edukacija", "Trošak", "Rok"]), 
                    key=f"d10_{eid}", 
                    num_rows="dynamic", 
                    use_container_width=True,
                    column_config={
                        "Trošak": st.column_config.TextColumn("Trošak", help="Unesite iznos (npr. 500 EUR)")
                    }
                )
                
                st.markdown("### 3. PODRŠKA")
                sup = st.text_input("Potrebna podrška:", d.get('support_needed',''), key=f"sup_{eid}")
                
                if st.button("💾 SPREMI IDP", key=f"b_idp_{eid}"):
                    try:
                        conn.close()
                        with sqlite3.connect(DB_FILE) as db:
                            j70 = table_to_json_string(d70.astype(str))
                            j20 = table_to_json_string(d20.astype(str))
                            j10 = table_to_json_string(d10.astype(str))
                            
                            db.execute("DELETE FROM development_plans WHERE kadrovski_broj=? AND period=?", (eid, current_period))
                            db.execute("""INSERT INTO development_plans 
                                (period, kadrovski_broj, manager_id, strengths, areas_improve, career_goal, 
                                 json_70, json_20, json_10, support_needed, support_notes, status, company_id) 
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
                                (current_period, eid, username, s, w, g, j70, j20, j10, sup, "", 'Active', 1))
                        
                        st.toast("IDP Spremljen!", icon="✅")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Greška kod spremanja: {e}")

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
                    conn.commit(); st.success("Poslano!")

        with t2:
            st.caption("Delegirajte procjenu Team Leadu ili Mentoru.")
            with st.form("del_form"):
                mentor = st.selectbox("Mentor:", my_team['ime_prezime'].tolist())
                target = st.selectbox("Koga procijeniti:", my_team['ime_prezime'].tolist())
                if st.form_submit_button("Delegiraj"):
                    mid = my_team[my_team['ime_prezime']==mentor]['kadrovski_broj'].values[0]
                    tid = my_team[my_team['ime_prezime']==target]['kadrovski_broj'].values[0]
                    conn.execute("INSERT INTO delegated_tasks (manager_id, delegate_id, target_id, period, status, company_id) VALUES (?,?,?,?,'Pending',1)", (username, mid, tid, current_period))
                    conn.commit(); st.success("Delegirano!")

    try: conn.close()
    except: pass