from database import get_db

conn = get_db()

conn.executescript("""
DROP TABLE IF EXISTS profil;

CREATE TABLE profil (
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

ALTER TABLE faktury ADD COLUMN uzivatel TEXT;
""")

conn.commit()
conn.close()

print("Databáze byla úspěšně opravena.")
