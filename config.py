import os

SECRET_KEY = 'nejake-tajne-heslo'
UPLOAD_FOLDER = 'static/uploads'

# Tajné přihlašovací údaje načítané ze serveru
ADMIN_USERNAME = os.environ.get('WEB_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('WEB_PASSWORD', 'admin123')


MAIL_SERVER = '://brevo.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USE_SSL = False
MAIL_USERNAME = 'rekonstrukceholy@seznam.cz'     # vaše celá adresa
MAIL_PASSWORD = 'HolySteoan777333.'   # speciální heslo vygenerované v Seznamu
MAIL_SERVER = '://brevo.com'

