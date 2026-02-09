import hashlib
import pandas as pd
import json
import streamlit as st
import sqlite3
from modules.database import DB_FILE

SECRET_SALT = "SaaS_Secure_Performance_2026"

def make_hashes(password):
    return hashlib.sha256(str.encode(password + SECRET_SALT)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

# STANDARDNA (FALLBACK) METRIKA
STANDARD_METRICS = {
    "p": [
        {"id": "P1", "title": "KPI i Ciljevi", "def": "Stupanj ostvarenja postavljenih kvantitativnih ciljeva.", "crit": "Za 5: Premašuje ciljeve za >20%."},
        {"id": "P2", "title": "Kvaliteta rada", "def": "Točnost, temeljitost i pouzdanost u izvršavanju zadataka.", "crit": "Za 5: Rad je bez grešaka, povjerenje je 100%."},
        {"id": "P3", "title": "Stručnost", "def": "Tehničko znanje i vještine potrebne za samostalan rad.", "crit": "Za 5: Ekspert u svom području, prenosi znanje drugima."},
        {"id": "P4", "title": "Odgovornost", "def": "Osjećaj vlasništva nad konačnim uspjehom zadatka ili projekta.", "crit": "Za 5: Ponaša se kao vlasnik, proaktivan je."},
        {"id": "P5", "title": "Suradnja", "def": "Dijeljenje informacija i timski rad.", "crit": "Za 5: Gradi mostove između odjela, pomaže kolegama."}
    ],
    "pot": [
        {"id": "POT1", "title": "Agilnost učenja", "def": "Brzina usvajanja novih znanja i prilagodba promjenama.", "crit": "Za 5: Uči izuzetno brzo, traži nove izazove."},
        {"id": "POT2", "title": "Autoritet / Utjecaj", "def": "Sposobnost utjecaja na druge bez formalne moći.", "crit": "Za 5: Prirodni lider, ljudi ga slušaju i poštuju."},
        {"id": "POT3", "title": "Šira slika", "def": "Razumijevanje kako vlastiti rad utječe na ciljeve tvrtke.", "crit": "Za 5: Razmišlja strateški, predlaže rješenja za cijelu firmu."},
        {"id": "POT4", "title": "Ambicija", "def": "Želja za napredovanjem i preuzimanjem veće odgovornosti.", "crit": "Za 5: Jasno pokazuje 'glad' za uspjehom i većom rolom."},
        {"id": "POT5", "title": "Stabilnost", "def": "Zadržavanje fokusa i smirenosti u stresnim situacijama.", "crit": "Za 5: Stijena u timu, fokusiran kad je najteže."}
    ]
}

def calculate_category(p, pot):
    try:
        p = float(p)
        pot = float(pot)
    except:
        return "N/A"
        
    if p>=4.5 and pot>=4.5: return "⭐️ Top Talent"
    elif p>=4 and pot>=3.5: return "🚀 High Performer"
    elif p>=3 and pot>=4: return "💎 Rastući potencijal"
    elif p>=3 and pot>=3: return "✅ Pouzdan suradnik"
    elif p<3 and pot>=3: return "🌱 Talent u razvoju"
    else: return "⚖️ Potrebno poboljšanje"

def render_metric_input(title, desc, crit, key_prefix, val=3, type="perf"):
    bg_color = "#e6f3ff" if type == "perf" else "#fff0e6"
    border_color = "#2196F3" if type == "perf" else "#FF9800"
    
    st.markdown(f"""
    <div style="background-color: {bg_color}; padding: 15px; border-radius: 5px; border-left: 5px solid {border_color}; margin-bottom: 10px;">
        <div style="font-weight: bold; font-size: 16px;">{title}</div>
        <div style="font-size: 13px; color: #444; margin-top: 5px;">{desc}</div>
        <div style="font-size: 12px; color: #666; font-style: italic; margin-top: 5px;">{crit}</div>
    </div>
    """, unsafe_allow_html=True)
    
    safe_val = 3
    try: safe_val = int(val)
    except: safe_val = 3
    return st.slider(f"Ocjena", 1, 5, safe_val, key=key_prefix)

def table_to_json_string(df):
    if df is None or df.empty: return "[]"
    return json.dumps(df.astype(str).to_dict(orient='records'), ensure_ascii=False)

def get_df_from_json(json_str, columns):
    try:
        data = json.loads(json_str) if json_str else []
        return pd.DataFrame(data, columns=columns)
    except: return pd.DataFrame(columns=columns)

# --- PAMETNI DOHVAT PITANJA ---
def get_active_survey_questions(period, company_id):
    conn = sqlite3.connect(DB_FILE)
    
    # 1. Ima li predložak za ovaj period?
    res = conn.execute("""
        SELECT t.id, t.name 
        FROM cycle_templates ct
        JOIN form_templates t ON ct.template_id = t.id
        WHERE ct.period_name = ? AND ct.company_id = ?
    """, (period, company_id)).fetchone()
    
    if not res:
        conn.close()
        return 'standard', STANDARD_METRICS
    
    template_id = res[0]
    
    # 2. Dohvati pitanja
    qs = pd.read_sql_query("SELECT * FROM form_questions WHERE template_id=? ORDER BY order_index", conn, params=(template_id,))
    conn.close()
    
    # --- FIX: Ako je predložak prazan (nema pitanja), vrati Standard! ---
    if qs.empty:
        return 'standard', STANDARD_METRICS
    
    # Inače složi dinamička pitanja
    dynamic_metrics = {"p": [], "pot": []}
    for _, row in qs.iterrows():
        q_obj = {
            "id": str(row['id']),
            "title": row['title'],
            "def": row['description'],
            "crit": row['criteria_desc']
        }
        if row['section'] == 'p': dynamic_metrics['p'].append(q_obj)
        else: dynamic_metrics['pot'].append(q_obj)
        
    return 'dynamic', dynamic_metrics

# Dodajem alias za kompatibilnost
METRICS = STANDARD_METRICS