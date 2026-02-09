import streamlit as st
import time
import hashlib
from modules.database import init_db, get_connection, log_action, get_hash
from modules.views_emp import render_employee_view
from modules.views_mgr import render_manager_view
from modules.views_hr import render_hr_view
from modules.views_admin import render_admin_view

# PROMJENA NAZIVA OVDJE
st.set_page_config(page_title="Talent App", layout="wide", page_icon="⭐")

# Inicijalizacija baze (ovo pokreće i auto-fix korisnika)
init_db()

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# --- EKRAN ZA PRIJAVU ---
if not st.session_state['logged_in']:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        # PROMJENA NAZIVA OVDJE
        st.title("⭐ Talent App")
        st.write("Sustav za upravljanje učinkom i razvojem")
        
        with st.form("login_form"):
            u = st.text_input("Korisničko ime (Kadrovski broj)")
            p = st.text_input("Lozinka", type="password")
            
            if st.form_submit_button("Prijava"):
                # Koristimo istu hash funkciju kao u database.py
                h = get_hash(p)
                
                # Provjera u bazi
                user = get_connection().execute(
                    "SELECT role, company_id, department FROM users WHERE username=? AND password=?", 
                    (str(u).strip(), h)
                ).fetchone()
                
                if user:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = u
                    st.session_state['role'] = user[0]
                    st.session_state['company_id'] = user[1]
                    st.session_state['department'] = user[2]
                    st.success(f"Dobrodošli, {u}!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("Neispravni podaci.")

# --- GLAVNI IZBORNIK NAKON PRIJAVE ---
else:
    role = st.session_state['role']
    
    # Sidebar zaglavlje
    with st.sidebar:
        st.write(f"👤 **{st.session_state['username']}**")
        st.caption(f"Uloga: {role}")
        st.markdown("---")
        
        if st.button("Odjava", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()
        st.markdown("---")

    # --- LOGIKA PRIKAZA PO ROLAMA ---

    if role == 'SuperAdmin':
        # SuperAdmin vidi SAMO Admin i HR
        mode = st.sidebar.radio("ODABERITE MODUL:", ["🛡️ Super Admin Konzola", "📊 HR Panel (Glavno)"])
        
        if mode == "🛡️ Super Admin Konzola":
            render_admin_view()
        else:
            render_hr_view()

    elif role == 'HR':
        # HR vidi HR panel i svoj profil
        mode = st.sidebar.radio("MODUL:", ["📊 HR Panel", "👤 Moj Profil (Zaposlenik)"])
        
        if mode == "📊 HR Panel":
            render_hr_view()
        else:
            render_employee_view()

    elif role == 'Manager':
        # Manager bira između vođenja tima i svog profila
        mode = st.sidebar.radio("PRIKAZ:", ["👔 Voditeljski pogled", "👤 Moj profil (Zaposlenik)"])
        
        if mode == "👔 Voditeljski pogled":
            render_manager_view()
        else:
            render_employee_view()

    else: 
        # Običan zaposlenik nema izbor, vidi samo svoj profil
        render_employee_view()