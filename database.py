import sqlite3

def init_db():
    conn = sqlite3.connect('safety_bot.db')
    cursor = conn.cursor()
    
    # 1. Bo'limlar jadvali (admin_telegram_id bilan)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        login TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        admin_telegram_id INTEGER DEFAULT NULL
    )
    ''')
    
    # 2. Ishchilar jadvali
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS workers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        department_id INTEGER,
        telegram_id INTEGER DEFAULT NULL,
        FOREIGN KEY (department_id) REFERENCES departments (id)
    )
    ''')
    
    # 3. Xavfsizlik vositalari jadvali (Worker o'rniga Department ga ulaymiz)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS safety_tools (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        department_id INTEGER,
        tool_name TEXT NOT NULL,
        expiry_date TEXT NOT NULL,
        FOREIGN KEY (department_id) REFERENCES departments (id)
    )
    ''')
    
    # 7 ta standart bo'limlar ro'yxati
    default_departments = [
        ("Tezkor Navbatchilik Bo'limi", "Djalolov", "Lazizbek"),
        ("1-tamirlash Bo'limi", "Muhiddinov", "Asliddin"),
        ("2-tamirlash Bo'limi", "Ahmedov", "Toyirjon"),
        ("3-tamirlash Bo'limi", "Xojiyev", "Abduvaxob"),
        ("4-tamirlash bo'limi", "Xolmatov", "Saidabror"),
        ("5-tamirlash bo'limi", "Mirzakarimov", "Ibrohim"),
        ("6-ko'p qavatli binolarga xizmat ko'rsatish bo'limi", "Ibragimov", "Nodirbek")
        ("7-DSHXKB Bo'limi","sharopov","Muhriddin")
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
    print("Baza yangi loyihaga muvofiq muvaffaqiyatli yangilandi!")
