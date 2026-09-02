import sqlite3

def get_db():
    conn = sqlite3.connect('faktury.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS profil (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                firma TEXT, ulice TEXT, mesto TEXT, ico TEXT, dic TEXT, ucet TEXT, logo TEXT
            )
        ''')
        
        # Hlavní tabulka faktur (přidán příznak přenesené daňové povinnosti)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS faktury (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cislo_faktury TEXT, datum_vystaveni TEXT, datum_splatnosti TEXT,
                odberatel_firma TEXT, odberatel_adresa TEXT, odberatel_ico TEXT, 
                odberatel_email TEXT, forma_uhrady TEXT, stav TEXT, 
                prenesena_daň TEXT, total_price REAL
            )
        ''')
        
        # Tabulka položek (přidána sazba DPH)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS polozky_faktury (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                faktura_id INTEGER, popis TEXT, mnozstvi REAL, cena_ks REAL, dph REAL,
                FOREIGN KEY(faktura_id) REFERENCES faktury(id)
            )
        ''')
        
        # Aktualizace starších databází na disku, pokud sloupce chybí
        try:
            conn.execute('ALTER TABLE faktury ADD COLUMN prenesena_dan TEXT')
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute('ALTER TABLE polozky_faktury ADD COLUMN dph REAL')
        except sqlite3.OperationalError:
            pass

        check = conn.execute('SELECT COUNT(*) FROM profil').fetchone()
        if check == 0 or (isinstance(check, sqlite3.Row) and check[0] == 0):
            conn.execute('''
                INSERT INTO profil (firma, ulice, mesto, ico, dic, ucet, logo)
                VALUES ('Vaše Firma s.r.o.', 'Hlavní 123', '123 45 Město', '12345678', 'CZ12345678', '123456789/0100', '')
            ''')
    conn.close()
