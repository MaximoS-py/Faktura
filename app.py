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

def login_required(f):
    def wrapper(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == 'admin123':
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            flash('Nesprávné přihlašovací údaje', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    conn = get_db()
    faktury = conn.execute('SELECT * FROM faktury ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('index.html', faktury=faktury)

@app.route('/profil', methods=['GET', 'POST'])
@login_required
def profil():
    conn = get_db()
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
            UPDATE profil SET firma=?, ulice=?, mesto=?, ico=?, dic=?, ucet=?, logo=? WHERE id=1
        ''', (firma, ulice, mesto, ico, dic, ucet, logo_filename))
        conn.commit()
        flash('Profil byl úspěšně aktualizován', 'success')
        return redirect(url_for('profil'))

    data_profilu = conn.execute('SELECT * FROM profil WHERE id=1').fetchone()
    conn.close()
    return render_template('profil.html', profil=data_profilu)

@app.route('/nova-faktura', methods=['GET', 'POST'])
@login_required
def nova_faktura():
    conn = get_db()
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
        dph_list = request.form.getlist('dph[]')  # Načtení DPH pro každou položku
        
        total_price = 0
        polozky_to_save = []
        
        for i in range(len(popisy)):
            if popisy[i].strip() != '':
                mnozstvi = float(mnozstvi_list[i]) if mnozstvi_list[i] else 0
                cena = float(ceny_list[i]) if ceny_list[i] else 0
                sazba_dph = float(dph_list[i]) if i < len(dph_list) else 21.0
                
                # Výpočet celkové ceny položky na základě DPH
                zaklad = mnozstvi * cena
                if prenesena_dan == 'ANO':
                    cena_s_dph = zaklad  # Daň se nepřipočítává
                else:
                    cena_s_dph = zaklad * (1 + (sazba_dph / 100))
                
                total_price += cena_s_dph
                polozky_to_save.append((popisy[i], mnozstvi, cena, sazba_dph))
        
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO faktury (cislo_faktury, datum_vystaveni, datum_splatnosti, odberatel_firma, odberatel_adresa, odberatel_ico, odberatel_email, forma_uhrady, stav, prenesena_dan, total_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (cislo, vystaveni, splatnost, o_firma, o_adresa, o_ico, o_email, forma_uhrady, stav, prenesena_dan, total_price))
        faktura_id = cursor.lastrowid
        
        for p in polozky_to_save:
            conn.execute('''
                INSERT INTO polozky_faktury (faktura_id, popis, mnozstvi, cena_ks, dph)
                VALUES (?, ?, ?, ?, ?)
            ''', (faktura_id, p[0], p[1], p[2], p[3]))
            
        conn.commit()
        conn.close()
        return redirect(url_for('faktura_detail', id=faktura_id))

    data_profilu = conn.execute('SELECT * FROM profil WHERE id=1').fetchone()
    conn.close()
    return render_template('formular.html', profil=data_profilu)


# Jméno funkce je přesně faktura_detail, což opravuje BuildError z obrázku
@app.route('/faktura/<int:id>')
@login_required
def faktura_detail(id):
    conn = get_db()
    faktura = conn.execute('SELECT * FROM faktury WHERE id=?', (id,)).fetchone()
    polozky = conn.execute('SELECT * FROM polozky_faktury WHERE faktura_id=?', (id,)).fetchall()
    profil_data = conn.execute('SELECT * FROM profil WHERE id=1').fetchone()
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
    faktura = conn.execute('SELECT * FROM faktury WHERE id=?', (id,)).fetchone()
    polozky = conn.execute('SELECT * FROM polozky_faktury WHERE faktura_id=?', (id,)).fetchall()
    profil_data = conn.execute('SELECT * FROM profil WHERE id=1').fetchone()
    conn.close()

    if not faktura['odberatel_email']:
        flash('Chyba: Odběratel nemá vyplněný e-mail!', 'error')
        return redirect(url_for('faktura_detail', id=id))

    try:
        qr_url = f"https://googleapis.com:{profil_data['ucet'].replace('/', '*')}*AM:{faktura['total_price']}*CC:CZK*X-VS:{faktura['cislo_faktury']}"
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

        with smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT) as server:
            server.login(config.SMTP_UZIVATEL, config.SMTP_HESLO)
            server.sendmail(config.SMTP_UZIVATEL, faktura['odberatel_email'], msg.as_string())

        flash(f"Faktura byla odeslána na e-mail {faktura['odberatel_email']}", 'success')
    except Exception as e:
        flash(f"Chyba při odesílání e-mailu: {str(e)}", 'error')

    return redirect(url_for('faktura_detail', id=id))

@app.route('/ares/<ico>')
@login_required
def ares_proxy(ico):
    if not ico.isdigit() or len(ico) != 8:
        return jsonify({'error': 'Neplatný formát IČO'}), 400
    try:
        url = f"https://ares.gov.cz{ico}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            sidlo = data.get('sidlo', {})
            ulice = sidlo.get('nazevUlice', sidlo.get('nazevObce', ''))
            cislo_p = sidlo.get('cisloDomovni', '')
            cislo_o = sidlo.get('cisloOrientacni', '')
            adresa = f"{ulice} {cislo_p}/{cislo_o}\n{sidlo.get('psc', '')} {sidlo.get('nazevObce', '')}"
            return jsonify({'firma': data.get('obchodniJmeno', ''), 'adresa': adresa})
        return jsonify({'error': 'Subjekt nenalezen'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/qr')
def get_qr():
    account_info = request.args.get('account', '')
    amount = request.args.get('amount', '0')
    vs = request.args.get('vs', '')
    try:
        account_number, bank_code = account_info.split('/')
        spayd = f"SPD*1.0*ACC:{bank_code}*{account_number}*AM:{float(amount):.2f}*CC:CZK*X-VS:{vs}*MSG:Platba faktury"
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=10, border=1)
        qr.add_data(spayd)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        return send_file(img_io, mimetype='image/png')
    except Exception as e:
        return f"Chyba: {str(e)}", 400

if __name__ == '__main__':
    app.run(debug=True, port=5000)
