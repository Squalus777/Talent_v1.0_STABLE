import sqlite3
import os
import json
import hashlib
import glob
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__)).replace("modules", "")
DB_FILE = os.path.join(BASE_DIR, 'talent_database.db')

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except: pass
    return conn

# --- HASH FUNKCIJA ---
def get_hash(text):
    return hashlib.sha256(str(text).strip().encode('utf-8')).hexdigest()

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # 1. KREIRANJE TABLICA
    c.execute('CREATE TABLE IF NOT EXISTS companies (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, subdomain TEXT, logo_url TEXT, plan_type TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, department TEXT, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS employees_master (kadrovski_broj TEXT PRIMARY KEY, ime_prezime TEXT, radno_mjesto TEXT, department TEXT, manager_id TEXT, company_id INTEGER, is_manager INTEGER DEFAULT 0, active INTEGER DEFAULT 1)')
    
    c.execute('''CREATE TABLE IF NOT EXISTS evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT, kadrovski_broj TEXT, ime_prezime TEXT, radno_mjesto TEXT, department TEXT, manager_id TEXT, 
        p1 REAL, p2 REAL, p3 REAL, p4 REAL, p5 REAL, pot1 REAL, pot2 REAL, pot3 REAL, pot4 REAL, pot5 REAL, 
        avg_performance REAL, avg_potential REAL, category TEXT, action_plan TEXT, status TEXT, feedback_date TEXT, company_id INTEGER, is_self_eval INTEGER DEFAULT 0,
        json_answers TEXT
    )''')
    try: c.execute("ALTER TABLE evaluations ADD COLUMN json_answers TEXT")
    except: pass

    c.execute('CREATE TABLE IF NOT EXISTS form_templates (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, description TEXT, created_at TEXT, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS form_questions (id INTEGER PRIMARY KEY AUTOINCREMENT, template_id INTEGER, section TEXT, title TEXT, description TEXT, criteria_desc TEXT, question_type TEXT, order_index INTEGER, weight REAL, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS cycle_templates (period_name TEXT, template_id INTEGER, company_id INTEGER, PRIMARY KEY (period_name, company_id))')
    c.execute('CREATE TABLE IF NOT EXISTS survey_answers (id INTEGER PRIMARY KEY AUTOINCREMENT, evaluation_id INTEGER, question_id INTEGER, score INTEGER, comment TEXT, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS goals (id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT, kadrovski_broj TEXT, manager_id TEXT, title TEXT, description TEXT, weight INTEGER, progress REAL, status TEXT, last_updated TEXT, deadline TEXT, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS goal_kpis (id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id INTEGER, description TEXT, weight INTEGER, progress REAL, deadline TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS development_plans (id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT, kadrovski_broj TEXT, manager_id TEXT, strengths TEXT, areas_improve TEXT, career_goal TEXT, json_70 TEXT, json_20 TEXT, json_10 TEXT, support_needed TEXT, support_notes TEXT, status TEXT, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS meeting_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, kadrovski_broj TEXT, manager_id TEXT, date TEXT, notes TEXT, action_items TEXT, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS recognitions (id INTEGER PRIMARY KEY AUTOINCREMENT, sender_id TEXT, receiver_id TEXT, message TEXT, timestamp TEXT, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS periods (period_name TEXT PRIMARY KEY, deadline TEXT, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS app_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, user TEXT, action TEXT, details TEXT, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS delegated_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, manager_id TEXT, delegate_id TEXT, target_id TEXT, period TEXT, status TEXT, company_id INTEGER)')

    # FIX: Osiguraj da defaultni period postoji i u tablici periods i u settings
    default_period = '2026-Q1'
    if c.execute("SELECT COUNT(*) FROM app_settings").fetchone()[0] == 0:
        c.execute("INSERT INTO app_settings (setting_key, setting_value, company_id) VALUES ('active_period', ?, 1)", (default_period,))
    
    # Ovo je falilo - moramo osigurati da period postoji u tablici periods da bi ga dropdown vidio
    c.execute("INSERT OR IGNORE INTO periods (period_name, deadline, company_id) VALUES (?, '2026-03-31', 1)", (default_period,))
    
    # ---------------------------------------------------------
    # 🔥 AUTOMATSKA INICIJALIZACIJA 🔥
    # ---------------------------------------------------------
    
    # 1. Osiguraj Admina
    admin_hash = get_hash("admin123")
    c.execute("INSERT OR REPLACE INTO users (username, password, role, department, company_id) VALUES ('admin', ?, 'SuperAdmin', 'System', 1)", (admin_hash,))
    c.execute("INSERT OR IGNORE INTO employees_master (kadrovski_broj, ime_prezime, radno_mjesto, department, manager_id, is_manager, active, company_id) VALUES ('admin', 'System Admin', 'System', 'System', '', 1, 1, 1)")

    # 2. Sinkronizacija korisnika koji nemaju login (Sigurna)
    default_hash = get_hash("lozinka123")
    c.execute("""
        INSERT INTO users (username, password, role, department, company_id)
        SELECT e.kadrovski_broj, ?, 
               CASE WHEN e.is_manager = 1 THEN 'Manager' ELSE 'Employee' END, 
               e.department, e.company_id
        FROM employees_master e
        LEFT JOIN users u ON e.kadrovski_broj = u.username
        WHERE u.username IS NULL AND e.kadrovski_broj != 'admin'
    """, (default_hash,))
    
    conn.commit()
    conn.close()

# --- SPREMANJE PROCJENA ---
def save_evaluation_json_method(company_id, period, employee_id, manager_id, user_data, 
                                scores_p, scores_pot, avg_p, avg_pot, category, 
                                action_plan, answers_dict, is_self_eval, target_status):
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT id FROM evaluations WHERE kadrovski_broj=? AND period=? AND is_self_eval=? AND company_id=?", 
                    (employee_id, period, 1 if is_self_eval else 0, company_id))
        row = cur.fetchone()
        json_str = json.dumps(answers_dict)
        
        # Dummy values za stare stupce (p1..p5)
        std_p = list(scores_p) if len(scores_p) == 5 else [0]*5
        std_pot = list(scores_pot) if len(scores_pot) == 5 else [0]*5
        while len(std_p) < 5: std_p.append(0)
        while len(std_pot) < 5: std_pot.append(0)

        if row:
            cur.execute("""UPDATE evaluations SET 
                avg_performance=?, avg_potential=?, category=?, 
                action_plan=?, feedback_date=?, status=?, json_answers=?
                WHERE id=?""", 
                (avg_p, avg_pot, category, action_plan, datetime.now().strftime("%Y-%m-%d"), target_status, json_str, row[0]))
        else:
            cur.execute("""INSERT INTO evaluations 
                (period, kadrovski_broj, ime_prezime, radno_mjesto, department, manager_id, 
                p1, p2, p3, p4, p5, pot1, pot2, pot3, pot4, pot5, 
                avg_performance, avg_potential, category, action_plan, status, feedback_date, company_id, is_self_eval, json_answers) 
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
                (period, employee_id, user_data.get('ime',''), user_data.get('radno_mjesto',''), user_data.get('odjel',''), manager_id,
                 std_p[0], std_p[1], std_p[2], std_p[3], std_p[4],
                 std_pot[0], std_pot[1], std_pot[2], std_pot[3], std_pot[4],
                 avg_p, avg_pot, category, action_plan, target_status, datetime.now().strftime("%Y-%m-%d"), company_id, 1 if is_self_eval else 0, json_str))

        conn.commit()
        conn.close()
        return True, "Spremljeno"
    except Exception as e: return False, str(e)

def save_evaluation_universal(*args, **kwargs):
    return save_evaluation_json_method(*args, **kwargs)

# --- OSTALO ---
def get_active_period_info():
    conn = get_connection()
    try:
        res = conn.execute("SELECT setting_value FROM app_settings WHERE setting_key='active_period'").fetchone()
        if res:
            period = res[0]
            dl = conn.execute("SELECT deadline FROM periods WHERE period_name=?", (period,)).fetchone()
            conn.close()
            return period, dl[0] if dl else ""
    except: pass
    conn.close()
    return "2026-Q1", ""

def log_action(user, action, details, company_id=1):
    try:
        with sqlite3.connect(DB_FILE, timeout=10) as conn:
            conn.execute("INSERT INTO audit_log (timestamp, user, action, details, company_id) VALUES (?,?,?,?,?)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user, action, details, company_id))
    except: pass

def perform_backup(auto=False):
    if not os.path.exists(DB_FILE): return False, "No DB"
    try:
        if not os.path.exists("backups"): os.makedirs("backups")
        prefix = "AUTO" if auto else "MANUAL"
        fname = f"backups/{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        src = get_connection(); dst = sqlite3.connect(fname); src.backup(dst); dst.close(); src.close()
        return True, fname
    except Exception as e: return False, str(e)

def get_available_backups():
    if not os.path.exists("backups"): return []
    return glob.glob("backups/*.db")