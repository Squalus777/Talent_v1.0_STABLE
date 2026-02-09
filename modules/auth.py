# auth.py (Ostaje skoro isti, samo mala provjera)
import streamlit as st
import pandas as pd
from modules.database import get_connection, perform_backup, log_action, get_active_period_info
from modules.utils import check_hashes

def login_screen():
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("🔴 Talent Management")
        
        current_period, _ = get_active_period_info()
        st.info(f"Aktivni period: **{current_period}**")
        
        u = st.text_input("Korisničko ime", key="login_user")
        p = st.text_input("Lozinka", type="password", key="login_pass")
        
        if st.button("Prijavi se", use_container_width=True):
            conn = get_connection()
            c = conn.cursor()
            data = c.execute("SELECT password, role, department, company_id FROM users WHERE username=?", (u,)).fetchone()
            conn.close()
            
            if data and check_hashes(p, data[0]):
                cid = data[3] if data[3] else 1
                st.session_state.update({
                    'logged_in': True, 
                    'username': u, 
                    'role': data[1], 
                    'department': data[2],
                    'company_id': cid
                })
                
                # Poziv log_action sada radi jer smo je dodali u database.py
                log_action(u, "LOGIN", "Prijava u sustav", company_id=cid)
                
                if data[1] == 'HR':
                    perform_backup(auto=True)
                
                st.rerun()
            else:
                st.error("Pogrešno korisničko ime ili lozinka.")
        
        st.markdown("---")
        st.caption("Verzija: 2.0 (Commercial Edition)")