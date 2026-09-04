import os
import io
import requests
import smtplib
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from flask import Flask, render_template, request, redirect, url_for, send_file, session, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from xhtml2pdf import pisa

import config
from database import get_db, init_db

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

init_db()


def login_required(f):
    def wrapper(*args, **kwargs):
        if 'logged_in' not in session or 'uzivatel' not in session:
            session.clear()
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


@app.route('/get-qr')
def get_qr():
    account = request.args.get('account', '')
    amount = request.args.get('amount', '0')
    vs = request.args.get('vs', '')

    formatted_account = account.replace('/', '*')
    payment_data = f"SPD*1.0*ACC:{formatted_account}*AM:{amount}*CC:CZK*X-VS:{vs}"
    encoded_data = urllib.parse.quote(payment_data, safe='')

    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded_data}"

    try:
        response = requests.get(qr_url, timeout=5)
        if response.status_code == 200:
            return send_file(io.BytesIO(response.content), mimetype='image/png')
    except Exception as e:
        print("QR ERROR:", e)

    return "QR kód se nepodařilo vygenerovat", 500


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        firma = request.form['firma'].strip()
        ico = request.form['ico'].strip()
        ucet = request.form['ucet'].strip()

        if not username or not password:
            flash('Uživatelské jméno a heslo jsou povinné!', 'error')
            return render_template('register.html')

        hashed_password = generate_password_hash(password)

        conn = get_db()
        try:
            conn.execute(
                'INSERT INTO uzivatele (username, password_hash) VALUES (?, ?)',
                (username, hashed_password)
            )
            conn.execute('''
                INSERT INTO profil (uzivatel, firma, ulice, mesto, ico, dic, ucet, logo)
                VALUES (?, ?, "", "", ?, "", ?, "")
            ''', (username, firma, ico, ucet))

            conn.commit()
            flash('Registrace byla úspěšná!', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Uživatelské jméno je již obsazené.', 'error')
        finally:
            conn.close()

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        conn = get_db()
        user = conn.execute('SELECT * FROM uzivatele WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['logged_in'] = True
            session['uzivatel'] = username
            return redirect(url_for('index'))
        else:
            flash('Nesprávné přihlašovací údaje', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    conn = get_db()
    uzivatel = session['uzivatel']
    faktury = conn.execute(
        'SELECT * FROM faktury WHERE uzivatel = ? ORDER BY id DESC',
        (uzivatel,)
    ).fetchall()
    conn.close()
    return render_template('index.html', faktury=faktury)


@app.route('/profil', methods=['GET', 'POST'])
@login_required
def profil():
    conn = get_db()
    uzivatel = session['uzivatel']

    profil_data = conn.execute('SELECT * FROM profil WHERE uzivatel=?', (uzivatel,)).fetchone()

    if request.method == 'POST':
        firma = request.form['firma']
        ulice = request.form['ulice']
        mesto = request.form['mesto']
        ico = request.form['ico']
        dic = request.form['dic']
        ucet = request.form['ucet']

        file = request.files.get('logo')
        logo_filename = profil_data['logo'] if profil_data else ""

        if file and file.filename:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            logo_filename = filename

        if profil_data:
            conn.execute('''
                UPDATE profil SET firma=?, ulice=?, mesto=?, ico=?, dic=?, ucet=?, logo=? WHERE uzivatel=?
            ''', (firma, ulice, mesto, ico, dic, ucet, logo_filename, uzivatel))
        else:
            conn.execute('''
                INSERT INTO profil (uzivatel, firma, ulice, mesto, ico, dic, ucet, logo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (uzivatel, firma, ulice, mesto, ico, dic, ucet, logo_filename))

        conn.commit()
        conn.close()
        flash("Profil uložen.", "success")
        return redirect(url_for('profil'))

    conn.close()
    return render_template('profil.html', profil=profil_data)


@app.route('/nova-faktura', methods=['GET', 'POST'])
@login_required
def nova_faktura():
    conn = get_db()
    uzivatel = session['uzivatel']

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

        popisy = request.form.getlist('popis[]')
        mnozstvi_list = request.form.getlist('mnozstvi[]')
        ceny_list = request.form.getlist('cena[]')
        dph_list = request.form.getlist('dph[]')

        total_price = 0
        polozky = []

        for i in range(len(popisy)):
            if popisy[i].strip():
                mnozstvi = float(mnozstvi_list[i])
                cena = float(ceny_list[i])
                dph = float(dph_list[i])

                zaklad = mnozstvi * cena
                celkem = zaklad if prenesena_dan == "ANO" else zaklad * (1 + dph / 100)

                total_price += celkem
                polozky.append((popisy[i], mnozstvi, cena, dph))

        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO faktury (uzivatel, cislo_faktury, datum_vystaveni, datum_splatnosti,
                                 odberatel_firma, odberatel_adresa, odberatel_ico, odberatel_email,
                                 forma_uhrady, stav, prenesena_dan, total_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (uzivatel, cislo, vystaveni, splatnost, o_firma, o_adresa, o_ico, o_email,
              forma_uhrady, "Nezaplaceno", prenesena_dan, total_price))

        faktura_id = cursor.lastrowid

        for p in polozky:
            conn.execute('''
                INSERT INTO polozky_faktury (faktura_id, popis, mnozstvi, cena_ks, dph)
                VALUES (?, ?, ?, ?, ?)
            ''', (faktura_id, p[0], p[1], p[2], p[3]))

        conn.commit()
        conn.close()
        return redirect(url_for('faktura_detail', id=faktura_id))

    profil_data = conn.execute('SELECT * FROM profil WHERE uzivatel=?', (uzivatel,)).fetchone()
    conn.close()
    return render_template('formular.html', profil=profil_data)


@app.route('/faktura/<int:id>')
@login_required
def faktura_detail(id):
    conn = get_db()
    uzivatel = session['uzivatel']

    faktura = conn.execute('SELECT * FROM faktury WHERE id=? AND uzivatel=?', (id, uzivatel)).fetchone()
    if not faktura:
        flash("Faktura nenalezena.", "error")
        return redirect(url_for('index'))

    polozky = conn.execute('SELECT * FROM polozky_faktury WHERE faktura_id=?', (id,)).fetchall()
    profil_data = conn.execute('SELECT * FROM profil WHERE uzivatel=?', (uzivatel,)).fetchone()

    conn.close()
    return render_template('faktura.html', faktura=faktura, polozky=polozky, profil=profil_data)


if __name__ == '__main__':
    app.run(debug=True)
