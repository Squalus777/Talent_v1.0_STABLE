# seed_data.py
import sqlite3
from modules.database import DB_FILE, init_db
from modules.utils import make_hashes

def seed():
    print("🚀 Pokrećem migraciju podataka i reset lozinki...")
    
    # 1. Inicijaliziraj tablice ako ne postoje
    init_db()
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 2. Obriši stare korisnike (opcionalno, ali preporučeno za testiranje)
    c.execute("DELETE FROM users")
    c.execute("DELETE FROM employees_master")
    
    # 3. Kreiraj nove lozinke s novim hashom
    admin_pass = make_hashes("admin123")
    user_pass = make_hashes("lozinka123")
    
    # 4. Ubaci osnovne korisnike
    users = [
        ('admin', admin_pass, 'SuperAdmin', 'System', 1),
        ('hr_user', user_pass, 'HR', 'HR', 1),
        ('mgr_user', user_pass, 'Manager', 'Prodaja', 1),
        ('emp_user', user_pass, 'Employee', 'Prodaja', 1)
    ]
    
    c.executemany("INSERT INTO users (username, password, role, department, company_id) VALUES (?,?,?,?,?)", users)
    
    # 5. Ubaci ih u master tablicu
    employees = [
        ('admin', 'System Admin', 'Admin', 'System', '', 1, 1, 1),
        ('hr_user', 'HR Voditelj', 'HR Manager', 'HR', '', 0, 1, 1),
        ('mgr_user', 'Glavni Manager', 'Sales Director', 'Prodaja', '', 1, 1, 1),
        ('emp_user', 'Zaposlenik Test', 'Sales Rep', 'Prodaja', 'mgr_user', 0, 1, 1)
    ]
    
    c.executemany("INSERT INTO employees_master (kadrovski_broj, ime_prezime, radno_mjesto, department, manager_id, is_manager, active, company_id) VALUES (?,?,?,?,?,?,?,?)", employees)
    
    conn.commit()
    conn.close()
    print("✅ Migracija završena! Sada se možete prijaviti s novim lozinkama.")

if __name__ == "__main__":
    seed()
