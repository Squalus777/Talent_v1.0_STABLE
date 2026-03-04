import sqlite3
import os

DB_FILE = 'talent_database.db'

def fix_database_complete():
    if not os.path.exists(DB_FILE):
        print(f"Baza {DB_FILE} nije pronađena! Pokrenite prvo app da se kreira.")
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    print("--- POČETAK POPRAVKA BAZE ---")
    
    try:
        # 1. Popravak tablice PERIODS (dodavanje is_active i start_date)
        try:
            c.execute("ALTER TABLE periods ADD COLUMN is_active INTEGER DEFAULT 0")
            print("✅ Dodano polje: is_active")
        except sqlite3.OperationalError:
            print("ℹ️ Polje is_active već postoji.")

        try:
            c.execute("ALTER TABLE periods ADD COLUMN start_date TEXT")
            print("✅ Dodano polje: start_date")
        except sqlite3.OperationalError:
            print("ℹ️ Polje start_date već postoji.")

        try:
            c.execute("ALTER TABLE periods ADD COLUMN end_date TEXT")
            print("✅ Dodano polje: end_date")
        except sqlite3.OperationalError:
            print("ℹ️ Polje end_date već postoji.")

        # 2. Postavljanje barem jednog perioda kao aktivnog (ako nema nijednog)
        active = c.execute("SELECT count(*) FROM periods WHERE is_active=1").fetchone()[0]
        if active == 0:
            # Ako nitko nije aktivan, postavi zadnji dodani period kao aktivan
            last = c.execute("SELECT period_name FROM periods ORDER BY rowid DESC LIMIT 1").fetchone()
            if last:
                c.execute("UPDATE periods SET is_active=1 WHERE period_name=?", (last[0],))
                print(f"✅ Postavljen defaultni aktivni period: {last[0]}")

        # 3. Provjera tablica za Upitnike (da spriječimo buduće greške)
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
        print("✅ Tablice za upitnike provjerene/kreirane.")

        conn.commit()
        print("\n🎉 GOTOVO! Baza je sada 100% usklađena s novim kodom.")
        
    except Exception as e:
        print(f"❌ Došlo je do greške: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_database_complete()