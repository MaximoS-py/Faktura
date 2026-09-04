import os

BASE_DIR = os.path.dirname(__file__)

SECRET_KEY = os.environ.get("SECRET_KEY", "render_secret_key")

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_UZIVATEL = os.environ.get("SMTP_UZIVATEL", "")
SMTP_HESLO = os.environ.get("SMTP_HESLO", "")
