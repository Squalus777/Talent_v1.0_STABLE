import sqlite3
import os

DB_FILE = 'talent_database.db'

def fix_database():
    if not os.path.exists(DB_FILE):
        print(f"Baza {DB_FILE} nije pronađena!")
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    try:
        # Dodajemo stupac start_date ako ne postoji
        try:
            c.execute("ALTER TABLE periods ADD COLUMN start_date TEXT")
            print("Dodano polje: start_date")
        except sqlite3.OperationalError:
            print("Polje start_date već postoji.")

        # Dodajemo stupac end_date ako ne postoji (za svaki slučaj)
        try:
            c.execute("ALTER TABLE periods ADD COLUMN end_date TEXT")
            print("Dodano polje: end_date")
        except sqlite3.OperationalError:
            print("Polje end_date već postoji.")
            
        conn.commit()
        print("✅ Baza je uspješno nadograđena!")
        
    except Exception as e:
        print(f"Došlo je do greške: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_database()