import sqlite3

def init_db():
    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    
    # Bo'limlar jadvali (admin_telegram_id bilan)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        login TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        admin_telegram_id INTEGER DEFAULT NULL
    )
    ''')
    
    # Ishchilar jadvali (telegram_id bilan)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS workers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        department_id INTEGER,
        telegram_id INTEGER DEFAULT NULL,
        FOREIGN KEY (department_id) REFERENCES departments (id)
    )
    ''')
    
    # Xavfsizlik vositalari jadvali
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS safety_tools (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worker_id INTEGER,
        tool_name TEXT NOT NULL,
        expiry_date TEXT NOT NULL,
        FOREIGN KEY (worker_id) REFERENCES workers (id)
    )
    ''')
    
    # Bo'limlar ro'yxati
    default_departments = [
        ("Tezkor Ta'mirlash Bo'limi", "dep1_admin", "parol123"),
        ("Yuqori Kuchlanish Bo'limi", "dep2_admin", "parol456"),
        ("Kabel Tarmoqlari Bo'limi", "dep3_admin", "parol789"),
        ("Rele Himoyasi Bo'limi", "dep4_admin", "parol111"),
        ("O'lchov va Metrologiya", "dep5_admin", "parol222"),
        ("Xavfsizlik Texnikasi Bo'limi", "dep6_admin", "parol333"),
        ("Logistika va Ta'minot", "dep7_admin", "parol444")
    ]
    
    for name, login, password in default_departments:
        try:
            cursor.execute('INSERT INTO departments (name, login, password) VALUES (?, ?, ?)', (name, login, password))
        except sqlite3.IntegrityError:
            pass
            
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Baza yangilandi va tayyor!")