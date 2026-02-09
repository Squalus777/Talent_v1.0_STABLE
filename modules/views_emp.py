import streamlit as st
import pandas as pd
import json
import plotly.express as px
import sqlite3
import time
from modules.database import get_connection, get_active_period_info, save_evaluation_json_method
from modules.utils import calculate_category, render_metric_input, get_df_from_json, get_active_survey_questions

def render_employee_view():
    conn = get_connection()
    current_period, deadline = get_active_period_info()
    username = st.session_state['username']
    company_id = st.session_state.get('company_id', 1)
    
    # INFO BAR
    st.info(f"📅 **AKTIVNO RAZDOBLJE:** {current_period}  |  ⏳ **ROK:** {deadline}")
    
    mode, survey_data = get_active_survey_questions(current_period, company_id)
    
    # Dohvat podataka o zaposleniku
    emp_res = conn.execute("SELECT ime_prezime, radno_mjesto, department FROM employees_master WHERE kadrovski_broj=?", (username,)).fetchone()
    my_name = emp_res[0] if emp_res else username
    
    st.header(f"👋 Dobrodošli, {my_name}")
    
    # TABS
    t1, t2, t3, t4, t5 = st.tabs(["📝 Samoprocjena", "📊 Gap Analiza", "🎯 Moji Ciljevi", "🚀 Moj IDP", "📜 Povijest"])

    # ----------------------------------------------------------------
    # 1. SAMOPROCJENA
    # ----------------------------------------------------------------
    with t1:
        st.subheader("Vaša samoprocjena")
        
        # Dohvati postojeću samoprocjenu
        r_df = pd.read_sql_query("SELECT * FROM evaluations WHERE kadrovski_broj=? AND period=? AND is_self_eval=1", conn, params=(username, current_period))
        r = r_df.iloc[0] if not r_df.empty else None
        
        # Provjeri je li zaključano (FIX: r is not None)
        is_submitted = r is not None and str(r['status']).strip() == 'Submitted'
        
        if is_submitted:
            st.success("✅ Vaša samoprocjena je poslana i zaključana.")
            c1, c2, c3 = st.columns(3)
            c1.metric("Moj Učinak", f"{r['avg_performance']:.2f}")
            c2.metric("Moj Potencijal", f"{r['avg_potential']:.2f}")
            st.info("Za detalje pogledajte tab 'Gap Analiza'.")
        else:
            # FORMA ZA UNOS
            with st.form("self_eval_form"):
                saved = {}
                # FIX: Eksplicitna provjera "is not None"
                if r is not None and r.get('json_answers'):
                    try: saved = json.loads(r['json_answers'])
                    except: pass
                
                scores_p = []
                scores_pot = []
                
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("### Učinak (Performance)")
                    for m in survey_data['p']:
                        val = int(saved.get(str(m['id']), 3))
                        s = render_metric_input(m['title'], m['def'], "", f"se_p_{m['id']}", val, "perf")
                        scores_p.append((str(m['id']), s))
                with c2:
                    st.markdown("### Potencijal (Potential)")
                    for m in survey_data['pot']:
                        val = int(saved.get(str(m['id']), 3))
                        s = render_metric_input(m['title'], m['def'], "", f"se_pot_{m['id']}", val, "pot")
                        scores_pot.append((str(m['id']), s))
                
                st.markdown("---")
                # DVA GUMBA: DRAFT I SUBMIT
                col_d, col_s = st.columns(2)
                is_draft = col_d.form_submit_button("💾 Spremi kao Nacrt")
                is_final = col_s.form_submit_button("✅ Pošalji i Zaključaj")
                
                if is_draft or is_final:
                    all_ans = {**dict(scores_p), **dict(scores_pot)}
                    vals_p = [x[1] for x in scores_p]; vals_pot = [x[1] for x in scores_pot]
                    ap = sum(vals_p)/len(vals_p) if vals_p else 0
                    apot = sum(vals_pot)/len(vals_pot) if vals_pot else 0
                    cat = calculate_category(ap, apot)
                    
                    target_status = "Submitted" if is_final else "Draft"
                    user_data = {'ime':emp_res[0],'radno_mjesto':emp_res[1],'odjel':emp_res[2]}
                    
                    conn.close()
                    save_evaluation_json_method(company_id, current_period, username, "Self", user_data, vals_p, vals_pot, ap, apot, cat, "", all_ans, True, target_status)
                    
                    if is_final:
                        st.balloons()
                        st.success("Samoprocjena uspješno poslana!")
                    else:
                        st.toast("Nacrt spremljen!", icon="💾")
                    time.sleep(1); st.rerun()

    # ----------------------------------------------------------------
    # 2. GAP ANALIZA
    # ----------------------------------------------------------------
    with t2:
        st.subheader("📊 Gap Analiza (Usporedba)")
        st.caption("Ovdje možete vidjeti razlike između vaše procjene i procjene voditelja.")
        
        # Dohvati Obje procjene
        my_eval = pd.read_sql_query("SELECT * FROM evaluations WHERE kadrovski_broj=? AND period=? AND is_self_eval=1", conn, params=(username, current_period))
        mgr_eval = pd.read_sql_query("SELECT * FROM evaluations WHERE kadrovski_broj=? AND period=? AND is_self_eval=0", conn, params=(username, current_period))
        
        if not my_eval.empty and not mgr_eval.empty:
            # Parsiraj JSON
            try:
                my_json = json.loads(my_eval.iloc[0]['json_answers'])
                mgr_json = json.loads(mgr_eval.iloc[0]['json_answers'])
                
                gap_data = []
                all_questions = survey_data['p'] + survey_data['pot']
                
                for q in all_questions:
                    qid = str(q['id'])
                    my_score = int(my_json.get(qid, 0))
                    mgr_score = int(mgr_json.get(qid, 0))
                    diff = mgr_score - my_score
                    
                    if diff < 0: status = "📉 Niža ocjena voditelja"
                    elif diff > 0: status = "📈 Viša ocjena voditelja"
                    else: status = "✅ Suglasni"
                    
                    gap_data.append({
                        "Sekcija": "Učinak" if q in survey_data['p'] else "Potencijal",
                        "Pitanje": q['title'],
                        "Ja": my_score,
                        "Voditelj": mgr_score,
                        "Razlika": diff,
                        "Status": status
                    })
                
                df_gap = pd.DataFrame(gap_data)
                
                c1, c2 = st.columns(2)
                c1.metric("Moja ocjena", f"{my_eval.iloc[0]['avg_performance']:.2f} / {my_eval.iloc[0]['avg_potential']:.2f}")
                if mgr_eval.iloc[0]['status'] == 'Submitted':
                    c2.metric("Ocjena Voditelja", f"{mgr_eval.iloc[0]['avg_performance']:.2f} / {mgr_eval.iloc[0]['avg_potential']:.2f}")
                else:
                    c2.warning("Voditelj još nije zaključao procjenu.")
                
                st.dataframe(df_gap.style.applymap(lambda x: 'background-color: #ffcccc' if x < 0 else ('background-color: #ccffcc' if x > 0 else ''), subset=['Razlika']), use_container_width=True)
                
            except Exception as e:
                st.error(f"Greška pri obradi podataka za analizu: {e}")
        else:
            st.info("Analiza će biti dostupna kada vi i vaš voditelj unesete procjene.")

    # ----------------------------------------------------------------
    # 3. CILJEVI
    # ----------------------------------------------------------------
    with t3:
        st.subheader("Moji Ciljevi")
        goals = pd.read_sql_query("SELECT * FROM goals WHERE kadrovski_broj=? AND period=?", conn, params=(username, current_period))
        if not goals.empty:
            for _, g in goals.iterrows():
                st.markdown(f"**{g['title']}** ({g['progress']}%)")
                st.progress(float(g['progress'])/100)
                st.caption(g['description'])
                # Prikaz KPI-a
                kpis = pd.read_sql_query("SELECT description, weight, progress FROM goal_kpis WHERE goal_id=?", conn, params=(g['id'],))
                if not kpis.empty:
                    st.dataframe(kpis.rename(columns={'description':'KPI', 'weight':'Težina', 'progress':'%'}), hide_index=True)
        else: st.info("Nemate dodijeljenih ciljeva.")

    # ----------------------------------------------------------------
    # 4. IDP
    # ----------------------------------------------------------------
    with t4:
        st.subheader("Razvojni plan (IDP)")
        res = conn.execute("SELECT * FROM development_plans WHERE kadrovski_broj=? AND period=?", (username, current_period)).fetchone()
        if res:
            cols = [c[1] for c in conn.execute("PRAGMA table_info(development_plans)").fetchall()]
            d = dict(zip(cols, res))
            st.info(f"🎯 **Karijerni cilj:** {d.get('career_goal')}")
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.success("70% Iskustvo")
                st.dataframe(get_df_from_json(d.get('json_70'), ["Aktivnost", "Rok"]), use_container_width=True, hide_index=True)
            with c2:
                st.warning("20% Mentoring")
                st.dataframe(get_df_from_json(d.get('json_20'), ["Aktivnost", "Rok"]), use_container_width=True, hide_index=True)
            with c3:
                st.error("10% Edukacija")
                st.dataframe(get_df_from_json(d.get('json_10'), ["Edukacija", "Rok"]), use_container_width=True, hide_index=True)
            
            if d.get('support_needed'):
                st.write(f"**Potrebna podrška:** {d.get('support_needed')}")
        else: st.warning("IDP nije definiran od strane voditelja.")

    # ----------------------------------------------------------------
    # 5. POVIJEST
    # ----------------------------------------------------------------
    with t5:
        st.subheader("Povijest procjena")
        hist = pd.read_sql_query("SELECT period, avg_performance, avg_potential FROM evaluations WHERE kadrovski_broj=? AND is_self_eval=0 AND status='Submitted'", conn, params=(username,))
        if not hist.empty: 
            st.plotly_chart(px.line(hist, x="period", y=["avg_performance", "avg_potential"], markers=True), use_container_width=True)
        else: st.info("Nema podataka.")
    
    try: conn.close()
    except: pass