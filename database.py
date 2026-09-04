import sqlite3

def get_db():
    conn = sqlite3.connect('faktury.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Tabulka uživatelů
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS uzivatele (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
    """)

    # Tabulka profilů
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profil (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uzivatel TEXT NOT NULL,
            firma TEXT,
            ulice TEXT,
            mesto TEXT,
            ico TEXT,
            dic TEXT,
            ucet TEXT,
            logo TEXT
        );
    """)

    # Tabulka faktur
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS faktury (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uzivatel TEXT NOT NULL,
            cislo_faktury TEXT,
            datum_vystaveni TEXT,
            datum_splatnosti TEXT,
            odberatel_firma TEXT,
            odberatel_adresa TEXT,
            odberatel_ico TEXT,
            odberatel_email TEXT,
            forma_uhrady TEXT,
            stav TEXT,
            prenesena_dan TEXT,
            total_price REAL
        );
    """)

    # Tabulka položek faktur
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS polozky_faktury (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faktura_id INTEGER,
            popis TEXT,
            mnozstvi REAL,
            cena_ks REAL,
            dph REAL
        );
    """)

    conn.commit()
    conn.close()
