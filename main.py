import streamlit as st
import time
import hashlib
from modules.database import init_db, get_connection, log_action, get_hash
from modules.views_emp import render_employee_view
from modules.views_mgr import render_manager_view
from modules.views_hr import render_hr_view
from modules.views_admin import render_admin_view

# Postavke stranice
st.set_page_config(page_title="Talent App", layout="wide", page_icon="⭐")

# Inicijalizacija baze
init_db()

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# --- EKRAN ZA PRIJAVU ---
if not st.session_state['logged_in']:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.title("⭐ Talent App")
        st.write("Sustav za upravljanje učinkom i razvojem")
        
        with st.form("login_form"):
            u = st.text_input("Korisničko ime")
            p = st.text_input("Lozinka", type="password")
            
            if st.form_submit_button("Prijava"):
                h = get_hash(p)
                
                # --- NOVO: Provjera je li korisnik aktivan (active=1) ---
                conn = get_connection()
                query = """
                    SELECT u.role, u.company_id, u.department 
                    FROM users u
                    JOIN employees_master e ON u.username = e.kadrovski_broj
                    WHERE u.username=? AND u.password=? AND e.active=1
                """
                user = conn.execute(query, (str(u).strip(), h)).fetchone()
                conn.close()
                
                if user:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = u
                    st.session_state['role'] = user[0]
                    st.session_state['company_id'] = user[1]
                    st.session_state['department'] = user[2]
                    
                    # Logiranje prijave
                    log_action(u, "LOGIN", "Uspješna prijava", user[1])
                    
                    st.success(f"Dobrodošli, {u}!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Neispravni podaci ili je korisnički račun neaktivan.")

# --- GLAVNI IZBORNIK NAKON PRIJAVE ---
else:
    role = st.session_state['role']
    
    with st.sidebar:
        st.write(f"👤 **{st.session_state['username']}**")
        st.caption(f"Uloga: {role}")
        st.markdown("---")
        if st.button("Odjava", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()
        st.markdown("---")

    # Rutiranje po rolama
    if role == 'SuperAdmin':
        mode = st.sidebar.radio("MODUL:", ["🛡️ Super Admin Konzola", "📊 HR Panel (Glavno)"])
        if mode == "🛡️ Super Admin Konzola": render_admin_view()
        else: render_hr_view()

    elif role == 'HR':
        mode = st.sidebar.radio("MODUL:", ["📊 HR Panel", "👤 Moj Profil"])
        if mode == "📊 HR Panel": render_hr_view()
        else: render_employee_view()

    elif role == 'Manager':
        mode = st.sidebar.radio("MODUL:", ["👔 Voditeljski pogled", "👤 Moj profil"])
        if mode == "👔 Voditeljski pogled": render_manager_view()
        else: render_employee_view()

    else: 
        render_employee_view()