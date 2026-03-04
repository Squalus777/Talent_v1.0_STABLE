import sqlite3
import os
# Uvozimo tvoje module kako bismo osigurali ispravnu strukturu baze
from modules.database import init_db, DB_FILE
from modules.utils import make_hashes

# 1. Prvo inicijaliziraj bazu (ovo kreira tablice ako ne postoje)
print("Inicijalizacija baze podataka...")
init_db()

# 2. Poveži se na bazu
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# 3. Generiraj hash lozinke
hashed_pass = make_hashes("admin123") 

# 4. Ubaci ili zamijeni admin korisnika
print("Resetiranje admin korisnika...")
cursor.execute("""
    INSERT OR REPLACE INTO users (username, password, role, department, company_id) 
    VALUES (?, ?, ?, ?, ?)
""", ("admin", hashed_pass, "HR", "Uprava", 1))

conn.commit()
conn.close()
print("✅ Uspjeh! Korisnik 'admin' (lozinka: admin123) je kreiran u tablici 'users'.")