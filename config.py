import os

SECRET_KEY = os.environ.get("SECRET_KEY", "tajny_klic_pro_faktury")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.example.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_UZIVATEL = os.environ.get("SMTP_UZIVATEL", "noreply@example.com")
SMTP_HESLO = os.environ.get("SMTP_HESLO", "heslo")
