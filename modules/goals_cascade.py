# modules/goals_cascade.py
# Cascade Goals - OKR hijerarhija: Org → Odjel/Manager → Zaposlenik

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
from modules.database import get_connection, DB_FILE
from modules.utils import normalize_progress
from modules.constants import MAX_TITLE_LENGTH, MAX_TEXT_LENGTH


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _progress_bar_html(pct, color="#2196F3", height=8):
    """Inline HTML progress bar."""
    pct = max(0, min(100, float(pct or 0)))
    bg = "#e8edf2"
    return f"""
    <div style="background:{bg};border-radius:99px;height:{height}px;width:100%;margin:4px 0 8px 0;">
      <div style="background:{color};width:{pct}%;height:{height}px;border-radius:99px;
                  transition:width .4s ease;min-width:{'4px' if pct>0 else '0'};"></div>
    </div>
    <div style="font-size:11px;color:#666;margin-bottom:4px;">{pct:.1f}% ostvareno</div>
    """

def _status_badge(pct):
    pct = float(pct or 0)
    if pct >= 100: return "✅ Završeno", "#27ae60"
    if pct >= 60:  return "🔄 U tijeku", "#2980b9"
    if pct >= 20:  return "⚡ Početo", "#e67e22"
    return "⬜ Nije početo", "#95a5a6"

def _weight_color(total_w):
    if total_w == 100: return "#27ae60"
    if total_w > 100:  return "#e74c3c"
    return "#e67e22"

def _recalc_parent_progress(conn, parent_id):
    """
    Propagira progress prema gore u hijerarhiji.
    Roditeljev progress = weighted average djece.
    """
    if not parent_id:
        return
    children = conn.execute(
        "SELECT weight, progress FROM goals WHERE parent_goal_id=?", (parent_id,)
    ).fetchall()
    if not children:
        return
    total_w = sum(c[0] for c in children)
    if total_w == 0:
        return
    weighted = sum((c[0] * (c[1] or 0)) / total_w for c in children)
    conn.execute(
        "UPDATE goals SET progress=?, last_updated=? WHERE id=?",
        (weighted, datetime.now().strftime("%Y-%m-%d"), parent_id)
    )
    # Rekurzivno gore
    grandparent = conn.execute("SELECT parent_goal_id FROM goals WHERE id=?", (parent_id,)).fetchone()
    if grandparent and grandparent[0]:
        _recalc_parent_progress(conn, grandparent[0])


def save_kpis_and_recalc(conn, goal_id, kpi_df, parent_goal_id=None):
    """Sprema KPI-eve, izračunava goal progress, propagira gore."""
    kpi_df['Težina (%)'] = pd.to_numeric(kpi_df['Težina (%)'], errors='coerce').fillna(0)
    kpi_df['Ostvarenje (%)'] = pd.to_numeric(kpi_df['Ostvarenje (%)'], errors='coerce').fillna(0)

    conn.execute("DELETE FROM goal_kpis WHERE goal_id=?", (goal_id,))
    weighted_sum = 0
    total_kpi_w = 0
    for _, row in kpi_df.iterrows():
        if str(row.get('KPI Naziv', '')).strip():
            w = float(row['Težina (%)'])
            p = float(row['Ostvarenje (%)'])
            conn.execute(
                "INSERT INTO goal_kpis (goal_id, description, weight, progress) VALUES (?,?,?,?)",
                (goal_id, str(row['KPI Naziv']), w, p)
            )
            weighted_sum += (w * p) / 100
            total_kpi_w += w

    conn.execute(
        "UPDATE goals SET progress=?, last_updated=? WHERE id=?",
        (weighted_sum, datetime.now().strftime("%Y-%m-%d"), goal_id)
    )
    _recalc_parent_progress(conn, parent_goal_id)
    conn.commit()
    return total_kpi_w


# ─────────────────────────────────────────────
# HR: ORGANIZACIJSKI CILJEVI
# ─────────────────────────────────────────────

def render_org_goals_hr(company_id, current_period):
    """
    HR/SuperAdmin sučelje za upravljanje organizacijskim ciljevima (vrh piramide).
    """
    conn = get_connection()

    st.markdown("""
    <div style="background:linear-gradient(135deg,#1a237e,#283593);padding:16px 20px;border-radius:10px;margin-bottom:20px;">
      <div style="color:#fff;font-size:18px;font-weight:700;">🏢 Organizacijski Ciljevi</div>
      <div style="color:#9fa8da;font-size:13px;margin-top:4px;">
        Ciljevi koje postavljate ovdje kaskadiraju prema managerima i zaposlenicima.
      </div>
    </div>
    """, unsafe_allow_html=True)

    org_goals = pd.read_sql_query(
        "SELECT * FROM goals WHERE level='org' AND period=? AND company_id=? ORDER BY id DESC",
        conn, params=(current_period, company_id)
    )

    # ── FORMA ZA NOVI ORG CILJ ──
    with st.expander("➕ Postavi novi organizacijski cilj", expanded=org_goals.empty):
        with st.form("new_org_goal"):
            c1, c2 = st.columns([3, 1])
            title = c1.text_input("Naziv cilja *", max_chars=MAX_TITLE_LENGTH,
                                   placeholder="npr. Povećati prihod za 20%")
            weight = c2.number_input("Težina (%)", 1, 100, 100,
                                      help="Za org. ciljeve obično 100% jer su na vrhu hijerarhije")
            desc = st.text_area("Opis / Kontekst", max_chars=MAX_TEXT_LENGTH,
                                 placeholder="Zašto je ovaj cilj važan? Kako ćemo ga mjeriti?")
            c3, c4 = st.columns(2)
            deadline = c3.date_input("Rok", value=date(int(current_period[:4]), 12, 31)
                                      if len(current_period) >= 4 else date.today())
            status = c4.selectbox("Status", ["On Track", "At Risk", "Behind", "Completed"])
            if st.form_submit_button("🏢 Kreiraj Organizacijski Cilj", use_container_width=True):
                if title.strip():
                    conn.execute(
                        """INSERT INTO goals (period, kadrovski_broj, manager_id, title, description,
                           weight, progress, status, last_updated, deadline, company_id, level, department)
                           VALUES (?,?,?,?,?,?,0,?,?,?,?,?,?)""",
                        (current_period, 'ORG', 'ORG', title.strip(), desc,
                         weight, status, datetime.now().strftime("%Y-%m-%d"),
                         str(deadline), company_id, 'org', None)
                    )
                    conn.commit()
                    st.success("✅ Organizacijski cilj kreiran!")
                    st.rerun()
                else:
                    st.error("Naziv je obavezan.")

    st.divider()

    # ── PRIKAZ ORG CILJEVA S KASKADNIM PREGLEDOM ──
    if org_goals.empty:
        st.info("📭 Nema postavljenih organizacijskih ciljeva za ovaj period.")
        conn.close()
        return

    for _, og in org_goals.iterrows():
        oid = og['id']
        prog = float(og['progress'] or 0)
        badge, badge_color = _status_badge(prog)

        # Koliko managera je linkano na ovaj cilj
        dept_goals = pd.read_sql_query(
            "SELECT * FROM goals WHERE parent_goal_id=? AND level='dept'", conn, params=(oid,)
        )
        n_linked = len(dept_goals)

        with st.container():
            st.markdown(f"""
            <div style="border:1px solid #c5cae9;border-left:5px solid #3f51b5;
                        border-radius:8px;padding:16px 20px;margin-bottom:8px;background:#fafbff;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                  <span style="font-size:16px;font-weight:700;color:#1a237e;">🏢 {og['title']}</span>
                  <span style="margin-left:12px;font-size:12px;background:{badge_color};
                               color:#fff;padding:2px 8px;border-radius:99px;">{badge}</span>
                </div>
                <div style="font-size:12px;color:#666;">
                  Rok: {og['deadline']} &nbsp;|&nbsp; {n_linked} odjel{'a' if n_linked!=1 else ''} linkan{'o' if n_linked!=1 else ''}
                </div>
              </div>
              <div style="color:#555;font-size:13px;margin-top:6px;">{og['description'] or ''}</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown(_progress_bar_html(prog, "#3f51b5", 10), unsafe_allow_html=True)

        col_edit, col_cascade, col_del = st.columns([2, 2, 1])

        with col_edit:
            with st.expander("✏️ Uredi"):
                with st.form(f"edit_og_{oid}"):
                    nt = st.text_input("Naziv", og['title'], max_chars=MAX_TITLE_LENGTH)
                    nd = st.text_area("Opis", og['description'] or '', max_chars=MAX_TEXT_LENGTH)
                    nstat = st.selectbox("Status", ["On Track","At Risk","Behind","Completed"],
                                         index=["On Track","At Risk","Behind","Completed"].index(og['status'])
                                         if og['status'] in ["On Track","At Risk","Behind","Completed"] else 0)
                    if st.form_submit_button("Spremi"):
                        conn.execute("UPDATE goals SET title=?,description=?,status=? WHERE id=?",
                                     (nt, nd, nstat, oid))
                        conn.commit()
                        st.success("Ažurirano!")
                        st.rerun()

        with col_cascade:
            with st.expander(f"🔗 Kaskadni pregled ({n_linked} odjel)"):
                if dept_goals.empty:
                    st.caption("Nema departmentalnih ciljeva linkanih na ovaj org. cilj.")
                else:
                    for _, dg in dept_goals.iterrows():
                        dp = float(dg['progress'] or 0)
                        emp_count = conn.execute(
                            "SELECT COUNT(*) FROM goals WHERE parent_goal_id=? AND level='employee'",
                            (dg['id'],)
                        ).fetchone()[0]
                        st.markdown(f"""
                        <div style="padding:8px 12px;background:#f3f4f6;border-radius:6px;
                                    border-left:3px solid #7986cb;margin-bottom:6px;">
                          <div style="font-weight:600;font-size:13px;">🏬 {dg['title']}</div>
                          <div style="font-size:11px;color:#666;">{emp_count} zaposlenik(a) linkano</div>
                        </div>
                        """, unsafe_allow_html=True)
                        st.markdown(_progress_bar_html(dp, "#7986cb", 6), unsafe_allow_html=True)

        with col_del:
            if st.button("🗑️", key=f"del_og_{oid}", help="Obriši org. cilj"):
                st.session_state[f"confirm_del_og_{oid}"] = True

        if st.session_state.get(f"confirm_del_og_{oid}"):
            st.warning(f"⚠️ Brisanjem org. cilja '{og['title']}' NE brišu se odjel/zaposlenik ciljevi, samo se odlinkaju.")
            cy, cn = st.columns(2)
            if cy.button("Da, obriši", key=f"yes_og_{oid}"):
                conn.execute("UPDATE goals SET parent_goal_id=NULL WHERE parent_goal_id=?", (oid,))
                conn.execute("DELETE FROM goals WHERE id=?", (oid,))
                conn.commit()
                st.rerun()
            if cn.button("Odustani", key=f"no_og_{oid}"):
                st.session_state[f"confirm_del_og_{oid}"] = False
                st.rerun()

        st.divider()

    conn.close()


# ─────────────────────────────────────────────
# MANAGER: CILJEVI TIMA — NOVI UX
# ─────────────────────────────────────────────

def render_team_goals_manager(username, company_id, current_period):
    """
    Manager sučelje za ciljeve tima s kaskadnim kontekstom.
    Layout: lijevo kontekst (org+dept cilj), desno forma/lista.
    """
    conn = get_connection()

    my_team = pd.read_sql_query(
        "SELECT * FROM employees_master WHERE manager_id=? AND company_id=? AND active=1",
        conn, params=(username, company_id)
    )

    # ── KONTEKSTUALNI PANEL VRHA ──
    org_goals = pd.read_sql_query(
        "SELECT * FROM goals WHERE level='org' AND period=? AND company_id=? ORDER BY id",
        conn, params=(current_period, company_id)
    )
    dept_goals_mine = pd.read_sql_query(
        "SELECT * FROM goals WHERE level='dept' AND manager_id=? AND period=?",
        conn, params=(username, current_period)
    )

    # Kontekstualni header
    st.markdown("""
    <div style="background:linear-gradient(135deg,#004d40,#00695c);padding:14px 20px;
                border-radius:10px;margin-bottom:16px;">
      <div style="color:#fff;font-size:17px;font-weight:700;">🎯 Upravljanje Ciljevima Tima</div>
      <div style="color:#80cbc4;font-size:12px;margin-top:3px;">
        Ciljevi zaposlenika doprinose ciljevima odjela, koji doprinose organizacijskim ciljevima.
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Tri taba
    tab_overview, tab_dept, tab_emp = st.tabs([
        "📊 Pregled hijerarhije", "🏬 Moji ciljevi odjela", "👤 Ciljevi zaposlenika"
    ])

    # ════════════════════════════════════════
    # TAB 1: PREGLED HIJERARHIJE
    # ════════════════════════════════════════
    with tab_overview:
        st.markdown("#### Kaskadni pregled — od organizacije do zaposlenika")

        if org_goals.empty:
            st.info("📭 HR još nije postavio organizacijske ciljeve za ovaj period.")
        else:
            for _, og in org_goals.iterrows():
                op = float(og['progress'] or 0)
                badge, bc = _status_badge(op)
                st.markdown(f"""
                <div style="background:linear-gradient(90deg,#e8eaf6,#fafafa);
                            border-left:6px solid #3f51b5;border-radius:8px;
                            padding:12px 16px;margin-bottom:4px;">
                  <span style="font-size:15px;font-weight:700;color:#1a237e;">🏢 {og['title']}</span>
                  <span style="float:right;font-size:11px;background:{bc};color:#fff;
                               padding:2px 8px;border-radius:99px;">{badge}</span>
                </div>
                """, unsafe_allow_html=True)
                st.markdown(_progress_bar_html(op, "#3f51b5", 8), unsafe_allow_html=True)

                # Odjel ciljevi linkovani na ovaj org cilj
                linked_dept = pd.read_sql_query(
                    "SELECT * FROM goals WHERE parent_goal_id=? AND level='dept'",
                    conn, params=(og['id'],)
                )
                for _, dg in linked_dept.iterrows():
                    is_mine = dg['manager_id'] == username
                    dp = float(dg['progress'] or 0)
                    border = "#00897b" if is_mine else "#78909c"
                    bg = "#e0f2f1" if is_mine else "#f5f5f5"
                    mine_label = " 👈 **Vaš**" if is_mine else ""
                    st.markdown(f"""
                    <div style="margin-left:24px;background:{bg};border-left:4px solid {border};
                                border-radius:6px;padding:10px 14px;margin-bottom:3px;">
                      <span style="font-size:13px;font-weight:600;color:#004d40;">🏬 {dg['title']}{mine_label}</span>
                      <span style="float:right;font-size:11px;color:#666;">Težina: {dg['weight']}%</span>
                    </div>
                    """, unsafe_allow_html=True)
                    st.markdown(
                        '<div style="margin-left:24px;">' +
                        _progress_bar_html(dp, border, 6) +
                        '</div>', unsafe_allow_html=True
                    )

                    # Zaposlenik ciljevi
                    emp_goals = pd.read_sql_query(
                        "SELECT g.*, e.ime_prezime FROM goals g "
                        "LEFT JOIN employees_master e ON g.kadrovski_broj = e.kadrovski_broj "
                        "WHERE g.parent_goal_id=? AND g.level='employee'",
                        conn, params=(dg['id'],)
                    )
                    for _, eg in emp_goals.iterrows():
                        ep = float(eg['progress'] or 0)
                        st.markdown(f"""
                        <div style="margin-left:48px;background:#fafafa;border-left:3px solid #aed6f1;
                                    border-radius:5px;padding:8px 12px;margin-bottom:2px;">
                          <span style="font-size:12px;color:#333;">👤 {eg.get('ime_prezime','?')} — {eg['title']}</span>
                          <span style="float:right;font-size:11px;color:#888;">{eg['weight']}% | {ep:.0f}%</span>
                        </div>
                        """, unsafe_allow_html=True)
                st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ════════════════════════════════════════
    # TAB 2: MOJI CILJEVI ODJELA
    # ════════════════════════════════════════
    with tab_dept:
        st.markdown("#### Vaši ciljevi na razini odjela")
        st.caption("Linkajte ih na organizacijski cilj kako bi se progress propagirao prema gore.")

        # Forma novi dept cilj
        with st.expander("➕ Dodaj cilj odjela", expanded=dept_goals_mine.empty):
            with st.form("new_dept_goal"):
                title_d = st.text_input("Naziv cilja odjela *", max_chars=MAX_TITLE_LENGTH,
                                         placeholder="npr. Smanjiti churn u Q1")
                desc_d = st.text_area("Opis", max_chars=MAX_TEXT_LENGTH)
                c1, c2, c3 = st.columns(3)
                weight_d = c1.number_input("Težina (%)", 1, 100, 25)
                deadline_d = c2.date_input("Rok")
                # Linkaj na org cilj
                org_opts = ["-- Bez linka --"] + [
                    f"{r['title']} (#{r['id']})" for _, r in org_goals.iterrows()
                ] if not org_goals.empty else ["-- Nema org. ciljeva --"]
                parent_sel = c3.selectbox("Linkovati na org. cilj:", org_opts)

                if st.form_submit_button("🏬 Kreiraj Cilj Odjela", use_container_width=True):
                    if title_d.strip():
                        parent_id = None
                        if parent_sel not in ["-- Bez linka --", "-- Nema org. ciljeva --"]:
                            try:
                                parent_id = int(parent_sel.split("(#")[1].rstrip(")"))
                            except:
                                parent_id = None
                        with sqlite3.connect(DB_FILE) as db:
                            db.execute(
                                """INSERT INTO goals (period, kadrovski_broj, manager_id, title,
                                   description, weight, progress, status, last_updated, deadline,
                                   company_id, level, parent_goal_id)
                                   VALUES (?,?,?,?,?,?,0,'On Track',?,?,?,?,?)""",
                                (current_period, username, username, title_d.strip(), desc_d,
                                 weight_d, datetime.now().strftime("%Y-%m-%d"), str(deadline_d),
                                 company_id, 'dept', parent_id)
                            )
                        st.success("✅ Cilj odjela kreiran!")
                        st.rerun()
                    else:
                        st.error("Naziv je obavezan.")

        # Prikaz dept ciljeva
        dept_goals_mine = pd.read_sql_query(
            "SELECT * FROM goals WHERE level='dept' AND manager_id=? AND period=?",
            conn, params=(username, current_period)
        )
        if dept_goals_mine.empty:
            st.info("Nema ciljeva odjela za ovaj period.")
        else:
            for _, dg in dept_goals_mine.iterrows():
                did = dg['id']
                dp = float(dg['progress'] or 0)
                badge, bc = _status_badge(dp)

                # Parent org cilj info
                parent_info = ""
                if dg['parent_goal_id']:
                    pr = conn.execute("SELECT title FROM goals WHERE id=?", (dg['parent_goal_id'],)).fetchone()
                    if pr:
                        parent_info = f"↗️ Doprinosi: **{pr[0]}**"

                # Koliko emp ciljeva je linkovano
                n_emp = conn.execute(
                    "SELECT COUNT(*) FROM goals WHERE parent_goal_id=? AND level='employee'", (did,)
                ).fetchone()[0]

                st.markdown(f"""
                <div style="border:1px solid #b2dfdb;border-left:5px solid #00897b;
                            border-radius:8px;padding:14px 18px;margin-bottom:6px;background:#f1fffe;">
                  <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                    <div>
                      <span style="font-size:15px;font-weight:700;color:#004d40;">🏬 {dg['title']}</span>
                      <span style="margin-left:10px;font-size:11px;background:{bc};color:#fff;
                                   padding:2px 8px;border-radius:99px;">{badge}</span>
                    </div>
                    <div style="font-size:11px;color:#777;text-align:right;">
                      Rok: {dg['deadline']}<br>{n_emp} emp. ciljeva
                    </div>
                  </div>
                  <div style="font-size:12px;color:#00695c;margin-top:5px;">{parent_info}</div>
                </div>
                """, unsafe_allow_html=True)
                st.markdown(_progress_bar_html(dp, "#00897b", 8), unsafe_allow_html=True)

                c_edit, c_link, c_del = st.columns([2, 2, 1])
                with c_edit:
                    with st.expander("✏️ Uredi"):
                        with st.form(f"edit_dg_{did}"):
                            nt = st.text_input("Naziv", dg['title'], max_chars=MAX_TITLE_LENGTH)
                            nd_desc = st.text_area("Opis", dg['description'] or '', max_chars=MAX_TEXT_LENGTH)
                            nw = st.number_input("Težina (%)", 1, 100, int(dg['weight'] or 25))
                            # Promjena linka
                            org_opts2 = ["-- Bez linka --"] + [
                                f"{r['title']} (#{r['id']})" for _, r in org_goals.iterrows()
                            ]
                            curr_idx = 0
                            if dg['parent_goal_id']:
                                for i, o in enumerate(org_opts2):
                                    if f"(#{dg['parent_goal_id']})" in o:
                                        curr_idx = i
                                        break
                            new_parent = st.selectbox("Linkano na org. cilj:", org_opts2, index=curr_idx)
                            if st.form_submit_button("Spremi"):
                                pid2 = None
                                if new_parent != "-- Bez linka --":
                                    try:
                                        pid2 = int(new_parent.split("(#")[1].rstrip(")"))
                                    except:
                                        pid2 = None
                                conn.execute(
                                    "UPDATE goals SET title=?,description=?,weight=?,parent_goal_id=? WHERE id=?",
                                    (nt, nd_desc, nw, pid2, did)
                                )
                                conn.commit()
                                st.success("Ažurirano!")
                                st.rerun()

                with c_del:
                    if st.button("🗑️", key=f"del_dg_{did}", help="Obriši"):
                        st.session_state[f"cdel_dg_{did}"] = True
                if st.session_state.get(f"cdel_dg_{did}"):
                    st.warning("Brisanjem se odlinkaju zaposlenički ciljevi.")
                    cy2, cn2 = st.columns(2)
                    if cy2.button("Da, briši", key=f"ydg_{did}"):
                        conn.execute("UPDATE goals SET parent_goal_id=NULL WHERE parent_goal_id=?", (did,))
                        conn.execute("DELETE FROM goals WHERE id=?", (did,))
                        conn.commit()
                        st.rerun()
                    if cn2.button("Odustani", key=f"ndg_{did}"):
                        st.session_state[f"cdel_dg_{did}"] = False
                        st.rerun()
                st.divider()

    # ════════════════════════════════════════
    # TAB 3: CILJEVI ZAPOSLENIKA
    # ════════════════════════════════════════
    with tab_emp:
        if my_team.empty:
            st.info("Nemate dodijeljenih zaposlenika.")
            conn.close()
            return

        # Selector zaposlenika — kartica stil
        st.markdown("#### Odaberi zaposlenika")
        emp_names = my_team['ime_prezime'].tolist()
        sel_emp_name = st.selectbox("Zaposlenik", emp_names, label_visibility="collapsed")
        sel_emp = my_team[my_team['ime_prezime'] == sel_emp_name].iloc[0]
        eid = sel_emp['kadrovski_broj']

        emp_goals = pd.read_sql_query(
            "SELECT g.*, og.title as parent_title FROM goals g "
            "LEFT JOIN goals og ON g.parent_goal_id = og.id "
            "WHERE g.kadrovski_broj=? AND g.period=? AND g.level='employee' "
            "ORDER BY g.id",
            conn, params=(eid, current_period)
        )

        total_w = emp_goals['weight'].sum() if not emp_goals.empty else 0
        w_color = _weight_color(total_w)

        # ── KONTEKSTUALNI PANEL (desno) + forma (lijevo) ──
        left_col, right_col = st.columns([3, 2])

        with right_col:
            # Kontekst panel
            st.markdown(f"""
            <div style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:10px;padding:16px;">
              <div style="font-weight:700;font-size:14px;margin-bottom:12px;color:#333;">
                📋 Kontekst: {sel_emp_name}
              </div>
            """, unsafe_allow_html=True)

            # Težina summary
            st.markdown(f"""
              <div style="display:flex;justify-content:space-between;align-items:center;
                          background:#fff;border-radius:8px;padding:10px 14px;
                          border:1px solid {w_color};margin-bottom:10px;">
                <span style="font-size:13px;color:#555;">Ukupna težina ciljeva</span>
                <span style="font-size:22px;font-weight:800;color:{w_color};">{int(total_w)}%</span>
              </div>
            """, unsafe_allow_html=True)
            if total_w > 100:
                st.error("⚠️ Prekoračeno 100%!")
            elif total_w == 100:
                st.success("✅ Savršeno raspoređeno")
            else:
                st.warning(f"Ostaje još {100 - total_w}% za rasporediti")

            st.markdown("</div>", unsafe_allow_html=True)

            # Već dodijeljeni ciljevi
            if not emp_goals.empty:
                st.markdown("**Dodijeljeni ciljevi:**")
                for _, g in emp_goals.iterrows():
                    gp = float(g['progress'] or 0)
                    badge2, bc2 = _status_badge(gp)
                    parent_lbl = f"↗️ {g['parent_title']}" if g.get('parent_title') else "Bez linka"
                    st.markdown(f"""
                    <div style="background:#fff;border:1px solid #e0e0e0;border-left:3px solid {bc2};
                                border-radius:6px;padding:8px 12px;margin-bottom:6px;">
                      <div style="font-size:13px;font-weight:600;color:#333;">{g['title']}</div>
                      <div style="font-size:11px;color:#888;margin-top:2px;">
                        Težina: {g['weight']}% &nbsp;|&nbsp; {badge2}
                      </div>
                      <div style="font-size:11px;color:#1976d2;margin-top:2px;">{parent_lbl}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    st.markdown(_progress_bar_html(gp, bc2, 5), unsafe_allow_html=True)

            # Ciljevi odjela (za linkovanje)
            if not dept_goals_mine.empty:
                st.markdown("**Ciljevi odjela (za linkovanje):**")
                for _, dg in dept_goals_mine.iterrows():
                    st.markdown(f"""
                    <div style="background:#e0f2f1;border-radius:5px;padding:6px 10px;
                                font-size:11px;margin-bottom:4px;color:#004d40;">
                      🏬 {dg['title']} — {float(dg['progress'] or 0):.0f}% ostvareno
                    </div>
                    """, unsafe_allow_html=True)

        with left_col:
            # ── FORMA NOVI CILJ ZAPOSLENIKA ──
            with st.expander("➕ Dodaj novi cilj", expanded=True):
                with st.form(f"new_emp_goal_{eid}"):
                    title_e = st.text_input("Naziv cilja *", max_chars=MAX_TITLE_LENGTH,
                                             placeholder="npr. Povećati konverziju za 15%")
                    desc_e = st.text_area("Opis / Kako mjeriti?", max_chars=MAX_TEXT_LENGTH,
                                           placeholder="Koji su KPI-evi? Što je dokaz uspjeha?")
                    c1e, c2e = st.columns(2)
                    remaining = max(1, 100 - int(total_w))
                    weight_e = c1e.number_input(
                        f"Težina (%) — preostalo: {100-int(total_w)}%",
                        1, 100, min(remaining, 25)
                    )
                    deadline_e = c2e.date_input("Rok")

                    # Linkaj na dept cilj
                    if not dept_goals_mine.empty:
                        dept_opts = ["-- Bez linka na cilj odjela --"] + [
                            f"{r['title']} (#{r['id']})" for _, r in dept_goals_mine.iterrows()
                        ]
                        dept_link = st.selectbox("↗️ Doprinosi cilju odjela:", dept_opts)
                    else:
                        dept_link = "-- Bez linka --"
                        st.info("💡 Kreirajte cilj odjela u tabu 'Moji ciljevi odjela' za kaskadni link.")

                    submitted = st.form_submit_button("✅ Dodaj Cilj", use_container_width=True)
                    if submitted:
                        if title_e.strip():
                            parent_id_e = None
                            if dept_link not in ["-- Bez linka na cilj odjela --", "-- Bez linka --"]:
                                try:
                                    parent_id_e = int(dept_link.split("(#")[1].rstrip(")"))
                                except:
                                    parent_id_e = None
                            with sqlite3.connect(DB_FILE) as db:
                                db.execute(
                                    """INSERT INTO goals (period, kadrovski_broj, manager_id, title,
                                       description, weight, progress, status, last_updated,
                                       deadline, company_id, level, parent_goal_id)
                                       VALUES (?,?,?,?,?,?,0,'On Track',?,?,?,?,?)""",
                                    (current_period, eid, username, title_e.strip(), desc_e,
                                     weight_e, datetime.now().strftime("%Y-%m-%d"),
                                     str(deadline_e), company_id, 'employee', parent_id_e)
                                )
                            _recalc_parent_progress(conn, parent_id_e)
                            conn.commit()
                            st.success(f"✅ Cilj '{title_e}' dodan za {sel_emp_name}!")
                            st.rerun()
                        else:
                            st.error("Naziv je obavezan.")

            # ── LISTA I UPRAVLJANJE POSTOJEĆIM CILJEVIMA ──
            if not emp_goals.empty:
                st.markdown("---")
                st.markdown("**Upravljanje postojećim ciljevima**")
                for _, g in emp_goals.iterrows():
                    gid = g['id']
                    gp = float(g['progress'] or 0)

                    with st.expander(f"{'✅' if gp>=100 else '🎯'} {g['title']} — {int(g['weight'])}% težine"):
                        tabs_g = st.tabs(["KPI-evi", "Uredi cilj"])

                        with tabs_g[0]:
                            kpis = pd.read_sql_query(
                                "SELECT description, weight, progress FROM goal_kpis WHERE goal_id=?",
                                conn, params=(gid,)
                            )
                            df_k = kpis.rename(columns={
                                'description': 'KPI Naziv',
                                'weight': 'Težina (%)',
                                'progress': 'Ostvarenje (%)'
                            }) if not kpis.empty else pd.DataFrame(
                                columns=['KPI Naziv', 'Težina (%)', 'Ostvarenje (%)']
                            )
                            ed_k = st.data_editor(df_k, key=f"kpi_{gid}",
                                                   num_rows="dynamic", use_container_width=True)

                            kpi_total_w = ed_k['Težina (%)'].apply(
                                lambda x: pd.to_numeric(x, errors='coerce') or 0
                            ).sum() if not ed_k.empty else 0

                            col_kpi_info, col_kpi_save = st.columns([2, 1])
                            if kpi_total_w != 100 and not ed_k.empty:
                                col_kpi_info.warning(f"⚠️ KPI težine = {kpi_total_w:.0f}% (cilj: 100%)")
                            else:
                                col_kpi_info.empty()

                            if col_kpi_save.button("💾 Spremi KPI", key=f"skpi_{gid}"):
                                total_kw = save_kpis_and_recalc(conn, gid, ed_k, g['parent_goal_id'])
                                if total_kw != 100:
                                    st.warning(f"Spremljeno (KPI težine = {total_kw:.0f}%)")
                                else:
                                    st.success("✅ Spremljeno i propagirano gore!")
                                st.rerun()

                        with tabs_g[1]:
                            with st.form(f"edit_eg_{gid}"):
                                nt_e = st.text_input("Naziv", g['title'], max_chars=MAX_TITLE_LENGTH)
                                nw_e = st.number_input("Težina (%)", 1, 100, int(g['weight'] or 25))
                                nd_e = st.text_area("Opis", g['description'] or '', max_chars=MAX_TEXT_LENGTH)

                                dept_opts2 = ["-- Bez linka --"] + [
                                    f"{r['title']} (#{r['id']})" for _, r in dept_goals_mine.iterrows()
                                ]
                                curr_idx2 = 0
                                if g['parent_goal_id']:
                                    for i2, o2 in enumerate(dept_opts2):
                                        if f"(#{g['parent_goal_id']})" in o2:
                                            curr_idx2 = i2
                                            break
                                new_parent_e = st.selectbox("Cilj odjela:", dept_opts2, index=curr_idx2)

                                ce1, ce2 = st.columns(2)
                                if ce1.form_submit_button("💾 Spremi"):
                                    pid_e2 = None
                                    if new_parent_e != "-- Bez linka --":
                                        try:
                                            pid_e2 = int(new_parent_e.split("(#")[1].rstrip(")"))
                                        except:
                                            pid_e2 = None
                                    conn.execute(
                                        "UPDATE goals SET title=?,weight=?,description=?,parent_goal_id=? WHERE id=?",
                                        (nt_e, nw_e, nd_e, pid_e2, gid)
                                    )
                                    _recalc_parent_progress(conn, pid_e2)
                                    conn.commit()
                                    st.success("Ažurirano!")
                                    st.rerun()
                                if ce2.form_submit_button("🗑️ Obriši cilj"):
                                    st.session_state[f"cdel_eg_{gid}"] = True

                            if st.session_state.get(f"cdel_eg_{gid}"):
                                st.error("Obrisati ovaj cilj i sve KPI-eve?")
                                cyd, cnd = st.columns(2)
                                if cyd.button("Da, obriši", key=f"yeg_{gid}"):
                                    conn.execute("DELETE FROM goal_kpis WHERE goal_id=?", (gid,))
                                    old_parent = g['parent_goal_id']
                                    conn.execute("DELETE FROM goals WHERE id=?", (gid,))
                                    conn.commit()
                                    _recalc_parent_progress(conn, old_parent)
                                    conn.commit()
                                    st.rerun()
                                if cnd.button("Odustani", key=f"neg_{gid}"):
                                    st.session_state[f"cdel_eg_{gid}"] = False
                                    st.rerun()

    conn.close()


# ─────────────────────────────────────────────
# EMPLOYEE: READ-ONLY HIJERARHIJA
# ─────────────────────────────────────────────

def render_goals_employee_context(username, company_id, current_period):
    """
    Zaposlenik vidi svoje ciljeve + kontekst odjel cilja kojeg doprinosi.
    """
    conn = get_connection()

    my_goals = pd.read_sql_query(
        """SELECT g.*, pg.title as dept_title, pg.progress as dept_progress,
                  og.title as org_title, og.progress as org_progress
           FROM goals g
           LEFT JOIN goals pg ON g.parent_goal_id = pg.id AND pg.level='dept'
           LEFT JOIN goals og ON pg.parent_goal_id = og.id AND og.level='org'
           WHERE g.kadrovski_broj=? AND g.period=? AND g.level='employee'
           ORDER BY g.id""",
        conn, params=(username, current_period)
    )

    if my_goals.empty:
        st.info("Nemate dodijeljenih ciljeva za ovaj period.")
        conn.close()
        return

    total_w = my_goals['weight'].sum()
    avg_prog = my_goals['progress'].mean()

    # Summary
    c1, c2, c3 = st.columns(3)
    c1.metric("Broj ciljeva", len(my_goals))
    c2.metric("Ukupna težina", f"{int(total_w)}%")
    c3.metric("Prosječno ostvarenje", f"{avg_prog:.1f}%")
    st.markdown(_progress_bar_html(avg_prog, "#2196F3", 10), unsafe_allow_html=True)
    st.divider()

    for _, g in my_goals.iterrows():
        gp = float(g['progress'] or 0)
        badge, bc = _status_badge(gp)

        # Kontekst lanca
        chain_html = ""
        if g.get('org_title'):
            chain_html += f"""<span style="font-size:11px;color:#7986cb;">🏢 {g['org_title']}</span>
                              <span style="color:#bbb;margin:0 6px">›</span>"""
        if g.get('dept_title'):
            chain_html += f"""<span style="font-size:11px;color:#00897b;">🏬 {g['dept_title']}</span>
                              <span style="color:#bbb;margin:0 6px">›</span>"""
        chain_html += f"""<span style="font-size:11px;font-weight:600;color:#333;">👤 Ovaj cilj</span>"""

        with st.container():
            st.markdown(f"""
            <div style="border:1px solid #e0e0e0;border-left:5px solid {bc};
                        border-radius:8px;padding:14px 18px;margin-bottom:4px;background:#fff;">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div style="font-size:15px;font-weight:700;color:#212121;">🎯 {g['title']}</div>
                <div style="text-align:right;">
                  <span style="font-size:11px;background:{bc};color:#fff;
                               padding:2px 8px;border-radius:99px;">{badge}</span><br>
                  <span style="font-size:11px;color:#888;margin-top:3px;">Težina: {g['weight']}%</span>
                </div>
              </div>
              <div style="margin-top:8px;padding:6px 10px;background:#f8f9fa;
                          border-radius:6px;font-size:11px;">{chain_html}</div>
              <div style="font-size:12px;color:#666;margin-top:8px;">{g['description'] or ''}</div>
              <div style="font-size:11px;color:#888;margin-top:4px;">Rok: {g['deadline']}</div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown(_progress_bar_html(gp, bc, 8), unsafe_allow_html=True)

        # KPI pregled (read-only)
        kpis = pd.read_sql_query(
            "SELECT description, weight, progress FROM goal_kpis WHERE goal_id=?",
            conn, params=(g['id'],)
        )
        if not kpis.empty:
            with st.expander("📊 KPI detalji"):
                st.dataframe(
                    kpis.rename(columns={
                        'description': 'KPI', 'weight': 'Težina (%)', 'progress': 'Ostvarenje (%)'
                    }),
                    hide_index=True, use_container_width=True
                )

        # Odjel progress (read-only kontekst)
        if g.get('dept_title'):
            dp = float(g.get('dept_progress') or 0)
            st.markdown(f"""
            <div style="background:#e0f2f1;border-radius:6px;padding:8px 12px;
                        font-size:12px;color:#004d40;margin-top:4px;">
              🏬 Ovaj cilj doprinosi odjelu: <b>{g['dept_title']}</b> — {dp:.1f}% ostvareno
            </div>
            """, unsafe_allow_html=True)

        st.divider()

    conn.close()
