# modules/database.py
import sqlite3
import os
import json
import glob
from datetime import datetime

# Importamo hash funkciju iz utils
from modules.utils import make_hashes as get_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__)).replace("modules", "")
DB_FILE = os.path.join(BASE_DIR, 'talent_database.db')

def get_connection():
    """Kreira konekciju s bazom uz Anti-Locking postavke (WAL mode)."""
    # Povećan timeout na 30 sekundi da se izbjegne "Database is locked"
    conn = sqlite3.connect(DB_FILE, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row  # Omogućuje pristup stupcima po imenu
    try:
        # WAL mode omogućuje istovremeno čitanje i pisanje bez zaključavanja
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")
    except Exception as e:
        print(f"Baza PRAGMA error: {e}")
    return conn

def init_db():
    """Inicijalizira baze podataka i tablice s NAJNOVIJOM shemom."""
    conn = get_connection()
    c = conn.cursor()
    
    # 1. Osnovne tablice
    c.execute('CREATE TABLE IF NOT EXISTS companies (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, subdomain TEXT, logo_url TEXT, plan_type TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, department TEXT, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS employees_master (kadrovski_broj TEXT PRIMARY KEY, ime_prezime TEXT, radno_mjesto TEXT, department TEXT, manager_id TEXT, company_id INTEGER, is_manager INTEGER DEFAULT 0, active INTEGER DEFAULT 1)')
    
    # 2. Evaluacije i Ciljevi
    c.execute('CREATE TABLE IF NOT EXISTS evaluations (id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT, kadrovski_broj TEXT, ime_prezime TEXT, radno_mjesto TEXT, department TEXT, manager_id TEXT, avg_performance REAL, avg_potential REAL, category TEXT, action_plan TEXT, status TEXT, feedback_date TEXT, company_id INTEGER, is_self_eval INTEGER DEFAULT 0, json_answers TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS goals (id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT, kadrovski_broj TEXT, manager_id TEXT, title TEXT, description TEXT, weight INTEGER, progress REAL, status TEXT, last_updated TEXT, deadline TEXT, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS goal_kpis (id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id INTEGER, description TEXT, weight INTEGER, progress REAL, deadline TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS development_plans (id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT, kadrovski_broj TEXT, manager_id TEXT, strengths TEXT, areas_improve TEXT, career_goal TEXT, json_70 TEXT, json_20 TEXT, json_10 TEXT, support_needed TEXT, support_notes TEXT, status TEXT, company_id INTEGER)')
    
    # 3. Postavke i Periodi (Ažurirana shema s is_active i datumima)
    c.execute('CREATE TABLE IF NOT EXISTS periods (period_name TEXT PRIMARY KEY, start_date TEXT, deadline TEXT, end_date TEXT, is_active INTEGER DEFAULT 0, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS app_settings (setting_key TEXT PRIMARY KEY, setting_value TEXT, company_id INTEGER)')
    
    # 4. Logovi i Pohvale
    c.execute('CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, user TEXT, action TEXT, details TEXT, company_id INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS recognitions (id INTEGER PRIMARY KEY AUTOINCREMENT, sender_id TEXT, receiver_id TEXT, message TEXT, timestamp TEXT, company_id INTEGER)')

    # 5. NOVO: Tablice za Dinamičke Upitnike (Dizajner)
    c.execute("""CREATE TABLE IF NOT EXISTS form_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                created_at TEXT,
                company_id INTEGER
              )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS form_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_id INTEGER,
                section TEXT,
                title TEXT,
                description TEXT,
                criteria_desc TEXT,
                order_index INTEGER,
                company_id INTEGER
              )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS cycle_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_name TEXT,
                template_id INTEGER,
                company_id INTEGER
              )""")
    
    # Inicijalni podaci (Bootstrap ako je baza prazna)
    default_period = '2026-Q1'
    # Provjera postoji li barem jedan period, ako ne, kreiraj ga i postavi kao aktivnog
    if c.execute("SELECT COUNT(*) FROM periods").fetchone()[0] == 0:
        c.execute("INSERT INTO periods (period_name, start_date, deadline, is_active, company_id) VALUES (?, ?, '2026-03-31', 1, 1)", 
                  (default_period, datetime.now().strftime("%Y-%m-%d")))
        # Postavi i u settings za svaki slučaj (legacy fallback)
        c.execute("INSERT OR IGNORE INTO app_settings (setting_key, setting_value, company_id) VALUES ('active_period', ?, 1)", (default_period,))
    
    conn.commit()
    conn.close()

def save_evaluation_json_method(company_id, period, employee_id, manager_id, user_data, 
                                scores_p, scores_pot, avg_p, avg_pot, category, 
                                action_plan, answers_dict, is_self_eval, target_status):
    """Centralizirana metoda za spremanje procjena."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # ensure_ascii=False osigurava ispravno spremanje hrvatskih znakova
        json_str = json.dumps(answers_dict, ensure_ascii=False)
        
        # Ako je self-eval, manager_id u tablici evaluations je zapravo ID radnika (ili pravi manager ID, ovisno o logici)
        # Ovdje zadržavamo originalnu logiku: manager_id polje u tablici čuva ID onoga tko je nadređen (za report)
        
        cur.execute("SELECT id FROM evaluations WHERE kadrovski_broj=? AND period=? AND is_self_eval=? AND company_id=?", 
                    (employee_id, period, 1 if is_self_eval else 0, company_id))
        row = cur.fetchone()

        if row:
            # UPDATE postojeće procjene
            cur.execute("""UPDATE evaluations SET 
                avg_performance=?, avg_potential=?, category=?, 
                action_plan=?, feedback_date=?, status=?, json_answers=?
                WHERE id=?""", 
                (avg_p, avg_pot, category, action_plan, datetime.now().strftime("%Y-%m-%d"), target_status, json_str, row[0]))
        else:
            # INSERT nove procjene
            # Pazi: user_data mora biti dict s ključevima 'ime', 'radno_mjesto', 'odjel'
            cur.execute("""INSERT INTO evaluations 
                (period, kadrovski_broj, ime_prezime, radno_mjesto, department, manager_id, 
                avg_performance, avg_potential, category, action_plan, status, feedback_date, company_id, is_self_eval, json_answers) 
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
                (period, employee_id, user_data.get('ime',''), user_data.get('radno_mjesto',''), user_data.get('odjel',''), manager_id,
                 avg_p, avg_pot, category, action_plan, target_status, datetime.now().strftime("%Y-%m-%d"), company_id, 1 if is_self_eval else 0, json_str))

        conn.commit()
        conn.close()
        return True, "Uspješno spremljeno"
    except Exception as e:
        return False, str(e)

def get_active_period_info():
    """
    Napredni dohvat aktivnog perioda.
    1. Prvo traži period koji ima is_active=1 u tablici periods.
    2. Ako nema, traži u app_settings.
    3. Ako nema, vraća hardcoded default.
    """
    conn = get_connection()
    try:
        # Prioritet 1: Tablica periods
        row = conn.execute("SELECT period_name, deadline FROM periods WHERE is_active=1 LIMIT 1").fetchone()
        if row:
            return row['period_name'], row['deadline']
        
        # Prioritet 2: App settings (Legacy)
        res = conn.execute("SELECT setting_value FROM app_settings WHERE setting_key='active_period'").fetchone()
        if res:
            period = res[0]
            dl = conn.execute("SELECT deadline FROM periods WHERE period_name=?", (period,)).fetchone()
            return period, dl['deadline'] if dl else ""
            
        return "2026-Q1", "2026-03-31"
    except Exception as e:
        print(f"Greška pri dohvatu perioda: {e}")
        return "2026-Q1", "2026-03-31"
    finally:
        conn.close()

def log_action(user, action, details, company_id=1):
    """Zapisuje akciju u audit log (za sigurnost i praćenje)."""
    try:
        conn = get_connection()
        conn.execute("INSERT INTO audit_log (timestamp, user, action, details, company_id) VALUES (?,?,?,?,?)", 
                     (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user, action, details, company_id))
        conn.commit()
        conn.close()
    except: pass

def perform_backup(auto=False):
    """Kreira sigurnosnu kopiju baze podataka."""
    if not os.path.exists(DB_FILE): return False, "Baza ne postoji"
    try:
        if not os.path.exists("backups"): os.makedirs("backups")
        prefix = "AUTO" if auto else "MANUAL"
        fname = f"backups/{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        
        src = get_connection()
        dst = sqlite3.connect(fname)
        src.backup(dst)
        dst.close()
        src.close()
        return True, fname
    except Exception as e:
        return False, str(e)

def get_available_backups():
    """Vraća listu dostupnih backup datoteka."""
    return glob.glob("backups/*.db")