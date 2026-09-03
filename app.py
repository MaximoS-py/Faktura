import os
import io
import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from flask import Flask, render_template, request, redirect, url_for, send_file, session, flash, jsonify
from werkzeug.utils import secure_filename
from xhtml2pdf import pisa

# Načtení externích modulů
import config
from database import get_db, init_db

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)

# Inicializace struktury DB
init_db()

# AUTOMATICKÁ OPRAVA DATABÁZE: Přidá sloupec 'uzivatel' do obou tabulek, pokud tam chybí
conn = get_db()
try:
    conn.execute('ALTER TABLE faktury ADD COLUMN uzivatel TEXT DEFAULT "admin";')
    conn.commit()
except Exception:
    pass

try:
    conn.execute('ALTER TABLE profil ADD COLUMN uzivatel TEXT DEFAULT "admin";')
    conn.commit()
except Exception:
    pass
conn.close()


def login_required(f):
    def wrapper(*args, **kwargs):
        # BEZPEČNOSTNÍ KONTROLA: Pokud chybí příznak přihlášení nebo jméno uživatele, vymažeme session a jdeme na login
        if 'logged_in' not in session or 'uzivatel' not in session:
            session.clear()
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

@app.route('/get-qr')
def get_qr():
    """Generuje QR platbu přes oficiální bezplatné API qr-platba.cz."""
    account = request.args.get('account', '')
    amount = request.args.get('amount', '0')
    vs = request.args.get('vs', '')

    formatted_account = account.replace('/', '*')
    qr_string = f"https://qr-platba.cz{formatted_account}&amount={amount}&currency=CZK&vs={vs}"
    
    try:
        response = requests.get(qr_string, timeout=5)
        if response.status_code == 200:
            return send_file(io.BytesIO(response.content), mimetype='image/png')
    except Exception as e:
        print(f"Chyba při stahování QR kódu: {e}")
        
    return "QR kód se nepodařilo vygenerovat", 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == 'admin' and password == 'admin123':
            session['logged_in'] = True
            session['uzivatel'] = username
            return redirect(url_for('index'))
        else:
            flash('Nesprávné přihlašovací údaje', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()  # Bezpečně smaže celou session
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    conn = get_db()
    # Bezpečné získání uživatele ze session (pokud by tam náhodou nebyl, dosadí se 'admin')
    aktualni_uzivatel = session.get('uzivatel', 'admin')
    
    faktury = conn.execute(
        'SELECT * FROM faktury WHERE uzivatel = ? ORDER BY id DESC', 
        (aktualni_uzivatel,)
    ).fetchall()
    conn.close()
    return render_template('index.html', faktury=faktury)

@app.route('/profil', methods=['GET', 'POST'])
@login_required
def profil():
    conn = get_db()
    aktualni_uzivatel = session.get('uzivatel', 'admin')
    
    if request.method == 'POST':
        firma = request.form['firma']
        ulice = request.form['ulice']
        mesto = request.form['mesto']
        ico = request.form['ico']
        dic = request.form['dic']
        ucet = request.form['ucet']
        
        file = request.files.get('logo')
        logo_filename = request.form.get('current_logo', '')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            logo_filename = filename

        conn.execute('''
            UPDATE profil SET firma=?, ulice=?, mesto=?, ico=?, dic=?, ucet=?, logo=? WHERE uzivatel=?
        ''', (firma, ulice, mesto, ico, dic, ucet, logo_filename, aktualni_uzivatel))
        conn.commit()
        flash('Profil byl úspěšně aktualizován', 'success')
        return redirect(url_for('profil'))

    data_profilu = conn.execute('SELECT * FROM profil WHERE uzivatel=?', (aktualni_uzivatel,)).fetchone()
    conn.close()
    return render_template('profil.html', profil=data_profilu)

@app.route('/nova-faktura', methods=['GET', 'POST'])
@login_required
def nova_faktura():
    conn = get_db()
    aktualni_uzivatel = session.get('uzivatel', 'admin')
    
    if request.method == 'POST':
        cislo = request.form['cislo_faktury']
        vystaveni = request.form['datum_vystaveni']
        splatnost = request.form['datum_splatnosti']
        o_firma = request.form['odberatel_firma']
        o_adresa = request.form['odberatel_adresa']
        o_ico = request.form['odberatel_ico']
        o_email = request.form['odberatel_email']
        forma_uhrady = request.form['forma_uhrady']
        prenesena_dan = request.form.get('prenesena_dan', 'NE')
        stav = "Nezaplaceno"
        
        popisy = request.form.getlist('popis[]')
        mnozstvi_list = request.form.getlist('mnozstvi[]')
        ceny_list = request.form.getlist('cena[]')
        dph_list = request.form.getlist('dph[]')
        
        total_price = 0
        polozky_to_save = []
        
        for i in range(len(popisy)):
            if popisy[i].strip() != '':
                mnozstvi = float(mnozstvi_list[i]) if mnozstvi_list[i] else 0
                cena = float(ceny_list[i]) if ceny_list[i] else 0
                sazba_dph = float(dph_list[i]) if i < len(dph_list) else 21.0
                
                zaklad = mnozstvi * cena
                if prenesena_dan == 'ANO':
                    cena_s_dph = zaklad
                else:
                    cena_s_dph = zaklad * (1 + (sazba_dph / 100))
                
                total_price += cena_s_dph
                polozky_to_save.append((popisy[i], mnozstvi, cena, sazba_dph))
        
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO faktury (uzivatel, cislo_faktury, datum_vystaveni, datum_splatnosti, odberatel_firma, odberatel_adresa, odberatel_ico, odberatel_email, forma_uhrady, stav, prenesena_dan, total_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (aktualni_uzivatel, cislo, vystaveni, splatnost, o_firma, o_adresa, o_ico, o_email, forma_uhrady, stav, prenesena_dan, total_price))
        faktura_id = cursor.lastrowid
        
        # OPAVENÝ CYKLUS: Hodnoty se z tuple rozbalují pod správnými indexy
        for p in polozky_to_save:
            conn.execute('''
                INSERT INTO polozky_faktury (faktura_id, popis, mnozstvi, cena_ks, dph)
                VALUES (?, ?, ?, ?, ?)
            ''', (faktura_id, p[0], p[1], p[2], p[3]))
            
        conn.commit()
        conn.close()
        return redirect(url_for('faktura_detail', id=faktura_id))

    data_profilu = conn.execute('SELECT * FROM profil WHERE uzivatel=?', (aktualni_uzivatel,)).fetchone()
    conn.close()
    return render_template('formular.html', profil=data_profilu)

@app.route('/faktura/<int:id>')
@login_required
def faktura_detail(id):
    conn = get_db()
    aktualni_uzivatel = session.get('uzivatel', 'admin')
    faktura = conn.execute('SELECT * FROM faktury WHERE id=? AND uzivatel=?', (id, aktualni_uzivatel)).fetchone()
    
    if not faktura:
        conn.close()
        flash('Faktura nebyla nalezena nebo k ní nemáte přístup.', 'error')
        return redirect(url_for('index'))
        
    polozky = conn.execute('SELECT * FROM polozky_faktury WHERE faktura_id=?', (id,)).fetchall()
    profil_data = conn.execute('SELECT * FROM profil WHERE uzivatel=?', (aktualni_uzivatel,)).fetchone()
    conn.close()
    return render_template('faktura.html', faktura=faktura, polozky=polozky, profil=profil_data)

@app.route('/faktura/<int:id>/smazat', methods=['POST'])
@login_required
def smazat_fakturu(id):
    conn = get_db()
    conn.execute('DELETE FROM polozky_faktury WHERE faktura_id=?', (id,))
    conn.execute('DELETE FROM faktury WHERE id=?', (id,))
    conn.commit()
    conn.close()
    flash('Faktura byla úspěšně smazána.', 'success')
    return redirect(url_for('index'))

@app.route('/faktura/<int:id>/zmenit-stav', methods=['POST'])
@login_required
def zmenit_stav(id):
    conn = get_db()
    faktura = conn.execute('SELECT stav FROM faktury WHERE id=?', (id,)).fetchone()
    novy_st = "Zaplaceno" if faktura['stav'] != "Zaplaceno" else "Nezaplaceno"
    conn.execute('UPDATE faktury SET stav=? WHERE id=?', (novy_st, id))
    conn.commit()
    conn.close()
    flash(f"Stav faktury změněn na: {novy_st}", 'success')
    return redirect(url_for('index'))

@app.route('/faktura/<int:id>/odeslat', methods=['POST'])
@login_required
def odeslat_email(id):
    conn = get_db()
    aktualni_uzivatel = session.get('uzivatel', 'admin')
    faktura = conn.execute('SELECT * FROM faktury WHERE id=?', (id,)).fetchone()
    polozky = conn.execute('SELECT * FROM polozky_faktury WHERE faktura_id=?', (id,)).fetchall()
    profil_data = conn.execute('SELECT * FROM profil WHERE uzivatel=?', (aktualni_uzivatel,)).fetchone()
    conn.close()

    if not faktura['odberatel_email']:
        flash('Chyba: Odběratel nemá vyplněný e-mail!', 'error')
        return redirect(url_for('faktura_detail', id=id))

    try:
        qr_url = url_for(
            'get_qr',
            account=profil_data['ucet'],
            amount=faktura['total_price'],
            vs=faktura['cislo_faktury'],
            _external=True
        )
        
        html_rendered = render_template('faktura.html', faktura=faktura, polozky=polozky, profil=profil_data, qr_override=qr_url)
        
        pdf_buffer = io.BytesIO()
        pisa.CreatePDF(io.StringIO(html_rendered), dest=pdf_buffer)
        pdf_buffer.seek(0)

        msg = MIMEMultipart()
        msg['From'] = config.SMTP_UZIVATEL
        msg['To'] = faktura['odberatel_email']
        msg['Subject'] = f"Faktura č. {faktura['cislo_faktury']} - {profil_data['firma']}"

        body = f"Dobrý den,\n\nv příloze Vám zasíláme fakturu č. {faktura['cislo_faktury']}.\n\nS pozdravem,\n{profil_data['firma']}"
        msg.attach(MIMEText(body, 'plain'))

        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_buffer.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename=faktura_{faktura['cislo_faktury']}.pdf")
        msg.attach(part)

        server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT)
        server.starttls()
        server.login(config.SMTP_UZIVATEL, config.SMTP_HESLO)
        server.sendmail(config.SMTP_UZIVATEL, faktura['odberatel_email'], msg.as_string())
        server.quit()

        flash('E-mail s fakturou byl úspěšně odeslán.', 'success')
    except Exception as e:
        flash(f"Chyba při odesílání e-mailu: {str(e)}", 'error')

    return redirect(url_for('faktura_detail', id=id))

if __name__ == '__main__':
    app.run(debug=True)

