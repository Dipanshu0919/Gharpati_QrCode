import base64
import csv
import datetime
import io
import os
import platform
import qrcode
import sqlite3
import re
import zipfile
from decimal import Decimal, InvalidOperation
from concurrent.futures import ProcessPoolExecutor
from functools import wraps
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, render_template, request, redirect, url_for, send_file, session, flash, jsonify
from urllib.parse import quote
import uuid
import threading
import time
import shutil

from dotenv import load_dotenv
load_dotenv()


APP_PORT = int(os.environ.get("APP_PORT", 1594))
STATIC_PATH = os.path.join(os.path.dirname(__file__), "static")

app = Flask(__name__, static_url_path='/static', static_folder=STATIC_PATH)
app.secret_key = "replace-with-a-secure-key"
app.config['SESSION_PERMANENT'] = False
DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")
SAMPLE_CSV_PATH = os.path.join(os.path.dirname(__file__), "sample_users.csv")

GP_NAME = "ग्रामपंचायत"
HELPLINE_NUMBER = ""

def load_gp_name():
    global GP_NAME, HELPLINE_NUMBER
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT gp_name, helpline_number FROM admins LIMIT 1')
        row = c.fetchone()
        conn.close()
        if row:
            if row['gp_name']:
                GP_NAME = row['gp_name']
            if row['helpline_number']:
                HELPLINE_NUMBER = row['helpline_number']
    except Exception:
        pass

def _worker_init():
    """Load GP_NAME and HELPLINE_NUMBER in each worker process so QR cards show correct name."""
    load_gp_name()


fields = {
    "midkatkram": "मिळकत क्र",
    "ghar_malkache_nav": "मालकाचे नाव",
    "gharpatti_magil": "घरपट्टी (मागील)",
    "gharpatti_chalu": "घरपट्टी (चालू)",
    "gharpatti_ekun": "घरपट्टी (एकूण)",
    "divabatti_magil": "दिवाबत्ती (मागील)",
    "divabatti_chalu": "दिवाबत्ती (चालू)",
    "divabatti_ekun": "दिवाबत्ती (एकूण)",
    "arogya_magil": "आरोग्य (मागील)",
    "arogya_chalu": "आरोग्य (चालू)",
    "arogya_ekun": "आरोग्य (एकूण)",
    "panipatti_magil": "पाणीपट्टी (मागील)",
    "panipatti_chalu": "पाणीपट्टी (चालू)",
    "panipatti_ekun": "पाणीपट्टी (एकूण)",
    "ekun_dene_rakkam": "एकूण येणे रक्कम",
}

@app.context_processor
def inject_globals():
    return {
        "fields": fields,
        "gp_name": GP_NAME,
        "helpline_number": HELPLINE_NUMBER,
    }

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login', next=request.path))
        return f(*args, **kwargs)
    return decorated

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    return conn, c

def init_db():
    conn, c = get_db()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            sr_no INTEGER PRIMARY KEY AUTOINCREMENT,
            midkatkram TEXT,
            ghar_malkache_nav TEXT,
            gharpatti_magil TEXT,
            gharpatti_chalu TEXT,
            gharpatti_ekun TEXT,
            divabatti_magil TEXT,
            divabatti_chalu TEXT,
            divabatti_ekun TEXT,
            arogya_magil TEXT,
            arogya_chalu TEXT,
            arogya_ekun TEXT,
            panipatti_magil TEXT,
            panipatti_chalu TEXT,
            panipatti_ekun TEXT,
            ekun_dene_rakkam TEXT,
            payment_ss TEXT DEFAULT NULL,
            payment_status TEXT DEFAULT "Pending"
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS janam_dakhla (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_sr_no INTEGER,
            service_type TEXT NOT NULL DEFAULT 'birth',
            applicant_name TEXT,
            applicant_name_marathi TEXT,
            applicant_name_english TEXT,
            mobile_number TEXT,
            child_name TEXT,
            father_name TEXT,
            mother_name TEXT,
            birth_date TEXT,
            child_gender TEXT,
            deceased_name TEXT,
            deceased_gender TEXT,
            death_date TEXT,
            husband_name TEXT,
            wife_name TEXT,
            marriage_date TEXT,
            marriage_place TEXT,
            certificate_name_marathi TEXT,
            certificate_name_english TEXT,
            family_head_marathi TEXT,
            poverty_line_number TEXT,
            relation_with_family_head TEXT,
            status TEXT DEFAULT "Pending",
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_sr_no) REFERENCES users(sr_no)
        )
    ''')
    existing_columns = [row['name'] for row in c.execute("PRAGMA table_info(janam_dakhla)")]
    required_columns = {
        'service_type': "TEXT NOT NULL DEFAULT 'birth'",
        'applicant_name': 'TEXT',
        'applicant_name_marathi': 'TEXT',
        'applicant_name_english': 'TEXT',
        'mobile_number': 'TEXT',
        'child_name': 'TEXT',
        'father_name': 'TEXT',
        'mother_name': 'TEXT',
        'birth_date': 'TEXT',
        'child_gender': 'TEXT',
        'deceased_name': 'TEXT',
        'deceased_gender': 'TEXT',
        'death_date': 'TEXT',
        'husband_name': 'TEXT',
        'wife_name': 'TEXT',
        'marriage_date': 'TEXT',
        'marriage_place': 'TEXT',
        'certificate_name_marathi': 'TEXT',
        'certificate_name_english': 'TEXT',
        'family_head_marathi': 'TEXT',
        'poverty_line_number': 'TEXT',
        'relation_with_family_head': 'TEXT',
        'status': 'TEXT DEFAULT "Pending"',
        'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
    }
    for column, definition in required_columns.items():
        if column not in existing_columns:
            c.execute(f"ALTER TABLE janam_dakhla ADD COLUMN {column} {definition}")
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gp_name TEXT NOT NULL,
            admin_name TEXT NOT NULL,
            admin_contact TEXT NOT NULL,
            admin_email TEXT NOT NULL UNIQUE,
            admin_password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            upi_id TEXT DEFAULT NULL,
            helpline_number TEXT DEFAULT NULL
        )
    ''')
    conn.commit()
    conn.close()

def insert_user(data):
    conn, c = get_db()
    dict_values = [y for x,y in data.items()]
    dict_keys = [x for x,y in data.items()]
    values = tuple(dict_values)
    keys = tuple(dict_keys)
    c.execute(f'''
        INSERT INTO users ({', '.join(keys)}) VALUES ({', '.join(['?']*len(values))})
    ''', values)
    del dict_values, dict_keys, values, keys
    conn.commit()
    conn.close()


def insert_users(rows):
    if not rows:
        return
    conn, c = get_db()
    keys = tuple(fields.keys())
    placeholders = ', '.join(['?'] * len(keys))
    values = [tuple(row[key] for key in keys) for row in rows]
    c.executemany(f'''
        INSERT INTO users ({', '.join(keys)}) VALUES ({placeholders})
    ''', values)
    conn.commit()
    conn.close()


def insert_janam_dakhla_request(data):
    conn, c = get_db()
    c.execute('''
        INSERT INTO janam_dakhla (
            user_sr_no,
            service_type,
            applicant_name,
            applicant_name_marathi,
            applicant_name_english,
            mobile_number,
            child_name,
            father_name,
            mother_name,
            birth_date,
            child_gender,
            deceased_name,
            deceased_gender,
            death_date,
            husband_name,
            wife_name,
            marriage_date,
            marriage_place,
            certificate_name_marathi,
            certificate_name_english,
            family_head_marathi,
            poverty_line_number,
            relation_with_family_head
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('user_sr_no'),
        data.get('service_type', 'birth'),
        data.get('applicant_name'),
        data.get('applicant_name_marathi'),
        data.get('applicant_name_english'),
        data.get('mobile_number'),
        data.get('child_name'),
        data.get('father_name'),
        data.get('mother_name'),
        data.get('birth_date'),
        data.get('child_gender'),
        data.get('deceased_name'),
        data.get('deceased_gender'),
        data.get('death_date'),
        data.get('husband_name'),
        data.get('wife_name'),
        data.get('marriage_date'),
        data.get('marriage_place'),
        data.get('certificate_name_marathi'),
        data.get('certificate_name_english'),
        data.get('family_head_marathi'),
        data.get('poverty_line_number'),
        data.get('relation_with_family_head'),
    ))
    conn.commit()
    conn.close()


def get_janam_dakhla_requests():
    conn, c = get_db()
    c.execute('SELECT * FROM janam_dakhla ORDER BY created_at DESC')
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def get_janam_dakhla_requests_by_user(user_sr_no):
    conn, c = get_db()
    c.execute('SELECT * FROM janam_dakhla WHERE user_sr_no = ? ORDER BY created_at DESC', (user_sr_no,))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def approve_janam_dakhla_request(request_id):
    conn, c = get_db()
    c.execute('UPDATE janam_dakhla SET status = ? WHERE id = ?', ('Approved', request_id))
    conn.commit()
    conn.close()


def to_amount(value):
    try:
        text = str(value).strip().replace(',', '')
        return Decimal(text) if text else Decimal('0')
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0')

def has_marathi(text):
    return bool(re.search(r'[\u0900-\u097F]', str(text)))


def get_font(size=24, text=None):

    is_windows = platform.system() == "Windows"

    if is_windows:

        # Windows font paths
        if text is not None and not has_marathi(text):
            font_files = [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/calibri.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
                "C:/Windows/Fonts/Nirmala.ttf",  # Marathi support
            ]
        else:
            font_files = [
                "C:/Windows/Fonts/Nirmala.ttf",  # Best for Marathi
                "C:/Windows/Fonts/mangal.ttf",
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
            ]

    else:

        # Linux font paths
        if text is not None and not has_marathi(text):
            font_files = [
                "/usr/share/fonts/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf",
                "/usr/share/fonts/google-noto/NotoSansDevanagari-Regular.ttf",
            ]
        else:
            font_files = [
                "/usr/share/fonts/google-noto/NotoSansDevanagari-Regular.ttf",
                "/usr/share/fonts/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf",
            ]

    for path in font_files:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except Exception:
            continue

    return ImageFont.load_default()

def draw_multilingual_text(draw, x, y, text, fill, size):
    segments = re.split(r'([\u0900-\u097F]+)', str(text))
    current_x = x
    for segment in segments:
        if not segment:
            continue
        font = get_font(size, text=segment)
        draw.text((current_x, y), segment, fill=fill, font=font)
        try:
            w = font.getlength(segment)
        except AttributeError:
            w = draw.textsize(segment, font=font)[0]
        current_x += w

def get_multilingual_text_width(draw, text, size):
    segments = re.split(r'([\u0900-\u097F]+)', str(text))
    total_w = 0
    for segment in segments:
        if not segment:
            continue
        font = get_font(size, text=segment)
        try:
            w = font.getlength(segment)
        except AttributeError:
            w = draw.textsize(segment, font=font)[0]
        total_w += w
    return total_w

def draw_fitted_title(draw, text, img_width, header_h, color):
    max_w = img_width - 40
    for size in range(38, 21, -1):
        w = get_multilingual_text_width(draw, text, size)
        if w <= max_w:
            y = (header_h - size) // 2
            draw_multilingual_text(draw, (img_width - w) // 2, y, text, color, size)
            return
    words = text.split(' ')
    best = None
    for split_idx in range(1, len(words)):
        line1 = ' '.join(words[:split_idx])
        line2 = ' '.join(words[split_idx:])
        for size in range(34, 16, -1):
            w1 = get_multilingual_text_width(draw, line1, size)
            w2 = get_multilingual_text_width(draw, line2, size)
            if w1 <= max_w and w2 <= max_w:
                if best is None or size > best[2]:
                    best = (line1, line2, size)
                break
    if best:
        line1, line2, size = best
        total_h = size * 2 + 6
        y0 = (header_h - total_h) // 2
        w1 = get_multilingual_text_width(draw, line1, size)
        w2 = get_multilingual_text_width(draw, line2, size)
        draw_multilingual_text(draw, (img_width - w1) // 2, y0, line1, color, size)
        draw_multilingual_text(draw, (img_width - w2) // 2, y0 + size + 6, line2, color, size)
    else:
        size = 18
        w = get_multilingual_text_width(draw, text, size)
        y = (header_h - size) // 2
        draw_multilingual_text(draw, (img_width - w) // 2, y, text, color, size)


def parse_receipt_date(payment_status):
    if not payment_status or payment_status == "Pending":
        return None
    try:
        match = re.search(r"\d{4}-\d{2}-\d{2}", payment_status)
        if not match:
            return payment_status
        raw_date = match.group(0)
        return datetime.datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d %B %Y (%d-%m-%Y)")
    except Exception:
        return payment_status


def normalize_amount(value):
    if value is None:
        return None
    raw = str(value).strip().replace(',', '')
    if not raw:
        return None
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    if amount <= 0:
        return None
    normalized = format(amount.normalize(), 'f')
    if '.' in normalized:
        normalized = normalized.rstrip('0').rstrip('.')
    return normalized


def build_upi_payment_uri(admin_upi_id, amount):
    normalized_amount = normalize_amount(amount)

    if not admin_upi_id or not normalized_amount:
        return None
    to_return = (
        "upi://pay"
        f"?pa={admin_upi_id.strip()}"
        "&pn=grampanchayat"
        f"&tn={quote('घरपट्टी भरणा', safe='')}"
        f"&am={normalized_amount}"
        "&cu=INR"
    )
    return to_return


def qr_data_url(payload):
    if not payload:
        return None
    buffer = qr_png_buffer(payload)
    return image_buffer_to_data_url(buffer)


def image_buffer_to_data_url(buffer):
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def qr_png_buffer(payload):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    buffer = io.BytesIO()
    qr_img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer


def draw_app_badges(draw, x, y, badges):
    gap = 12
    badge_h = 44
    current_x = x
    for badge in badges:
        label = badge["label"]
        short = badge["short"]
        fill = badge["fill"]
        text_color = badge.get("text_color", "#ffffff")
        label_w = get_multilingual_text_width(draw, label, 18)
        short_w = get_multilingual_text_width(draw, short, 16)
        badge_w = 20 + 34 + 10 + max(label_w, short_w) + 20
        draw.rounded_rectangle(
            [current_x, y, current_x + badge_w, y + badge_h],
            radius=22,
            fill=fill,
            outline=fill
        )
        draw.ellipse([current_x + 10, y + 8, current_x + 34, y + 32], fill="#ffffff")
        draw_multilingual_text(draw, current_x + 16, y + 10, short, fill, 16)
        draw_multilingual_text(draw, current_x + 48, y + 12, label, text_color, 18)
        current_x += badge_w + gap


def generate_upi_qr_card_image(user, upi_payment_uri):
    user_dict = dict(user)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(upi_payment_uri)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    try:
        resample_method = Image.Resampling.LANCZOS
    except AttributeError:
        resample_method = Image.LANCZOS

    qr_img = qr_img.resize((400, 400), resample_method)

    width = 900
    height = 900
    background = Image.new('RGB', (width, height), '#ffffff')
    draw = ImageDraw.Draw(background)

    draw.rectangle([0, 0, width, height], fill='#ffffff')
    draw.rectangle([0, 0, width - 1, height - 1], outline='#cbd5e1', width=3)
    draw.rectangle([0, 0, width, 120], fill='#1e3a8a')

    draw_fitted_title(draw, GP_NAME, width, 65, '#ffffff')
    subtitle = "UPI पेमेंट QR"
    subtitle_w = get_multilingual_text_width(draw, subtitle, 24)
    draw_multilingual_text(draw, (width - subtitle_w) // 2, 72, subtitle, '#dbeafe', 24)

    qr_x = (width - 360) // 2 - 25
    qr_y = 153
    background.paste(qr_img, (qr_x, qr_y))

    badges = [
        {"label": "PhonePe", "short": "P", "fill": "#5f259f"},
        {"label": "Google Pay", "short": "G", "fill": "#1a73e8"},
        {"label": "Paytm", "short": "P", "fill": "#00baf2"},
        {"label": "BHIM", "short": "B", "fill": "#0f6bff"},
    ]
    badge_x = qr_x + 430
    badge_y = qr_y - -50
    for badge in badges:
        draw_app_badges(draw, badge_x, badge_y, [badge])
        badge_y += 60

    draw.rounded_rectangle([60, 600, width - 60, 710], radius=24, fill='#eff6ff', outline='#bfdbfe', width=2)
    owner_label = "घर मालकाचे नाव"
    owner_label_w = get_multilingual_text_width(draw, owner_label, 24)
    draw_multilingual_text(draw, (width - owner_label_w) // 2, 610, owner_label, '#1d4ed8', 24)
    owner_name = user_dict.get('ghar_malkache_nav') or '-'
    owner_name_w = get_multilingual_text_width(draw, owner_name, 32)
    draw_multilingual_text(draw, (width - owner_name_w) // 2, 640, owner_name, '#0f172a', 32)

    prop_no = f"मालमत्ता क्र. {user_dict.get('midkatkram') or '-'}"
    prop_no_w = get_multilingual_text_width(draw, prop_no, 22)
    draw_multilingual_text(draw, (width - prop_no_w) // 2, 675, prop_no, '#475569', 22)

    footer_text = 'वेळेत कर भरा आणि गावचा विकास साधा'
    if HELPLINE_NUMBER:
        footer_text += f'  |  हेल्पलाइन: {HELPLINE_NUMBER}'
    footer_w = get_multilingual_text_width(draw, footer_text, 20)
    draw_multilingual_text(draw, (width - footer_w) // 2, 750, footer_text, '#1e3a8a', 20)

    output = io.BytesIO()
    background.save(output, format='PNG')
    output.seek(0)
    return output


def generate_qr_card_image(user, base_url=None):
    user_dict = dict(user)
    if base_url:
        qr_url = f"{base_url.rstrip('/')}/user/{user_dict['sr_no']}"
    else:
        qr_url = url_for('view_user', sr_no=user_dict['sr_no'], _external=True)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='black', back_color='white').convert('RGB')
    try:
        resample_method = Image.Resampling.LANCZOS
    except AttributeError:
        resample_method = Image.LANCZOS

    qr_img = qr_img.resize((300, 300), resample_method)

    width = 900
    height = 610
    background = Image.new('RGB', (width, height), '#ffffff')
    draw = ImageDraw.Draw(background)

    header_h = 100
    draw.rectangle([0, 0, width, header_h], fill='#1e3a8a')
    draw.rectangle([0, 0, width-1, height-1], outline='#cbd5e1', width=3)

    title_text = GP_NAME + ' - घरपट्टी माहिती'
    draw_fitted_title(draw, title_text, width, header_h, '#ffffff')

    qr_x = 50
    qr_y = 120
    background.paste(qr_img, (qr_x, qr_y))
    draw.rectangle([qr_x-2, qr_y-2, qr_x+301, qr_y+301], outline='#cbd5e1', width=2)

    detail_x = qr_x + 300 + 60
    detail_y = 160

    entries = [
        ('मालकाचे नाव', user['ghar_malkache_nav'] or '-'),
        ('मालमत्ता क्र.', user['midkatkram'] or '-'),
    ]

    for index, (title, value) in enumerate(entries):
        draw_multilingual_text(draw, detail_x, detail_y, f'{title} :', '#64748b', 24)
        draw_multilingual_text(draw, detail_x, detail_y + 35, str(value), '#0f172a', 32)
        detail_y += 100

    inst_x = 50
    inst_y = 450

    draw.rectangle([30, inst_y - 20, width - 30, inst_y + 90], fill='#fff7ed', outline='#fed7aa', width=2)

    inst_title = "घरपट्टीची रक्कम QR कोडद्वारे भरण्याचे टप्पे :"
    draw_multilingual_text(draw, inst_x, inst_y - 5, inst_title, '#c2410c', 24)

    steps = [
        "- Google Scanner वापरून QR Code स्कॅन करा."
    ]

    step_y = inst_y + 40
    for step in steps:
        draw_multilingual_text(draw, inst_x, step_y, step, '#431407', 22)

    draw.line([0, height - 60, width, height - 60], fill='#e2e8f0', width=2)

    footer_text = 'वेळेत कर भरा आणि गावचा विकास साधा'
    if HELPLINE_NUMBER:
        footer_text += f'  |  हेल्पलाइन: {HELPLINE_NUMBER}'
    footer_w = get_multilingual_text_width(draw, footer_text, 22)
    draw_multilingual_text(draw, (width - footer_w) // 2, height - 45, footer_text, '#1e3a8a', 22)

    output = io.BytesIO()
    background.save(output, format='PNG')
    output.seek(0)
    return output


def admin_exists():
    conn, c = get_db()
    c.execute('SELECT id FROM admins LIMIT 1')
    row = c.fetchone()
    conn.close()
    return row is not None


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('admin_logged_in'):
        return redirect(url_for('dashboard'))

    setup_mode = not admin_exists()
    error = None
    email = ''

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if setup_mode:
            gp_name       = request.form.get('gp_name', '').strip()
            admin_name    = request.form.get('admin_name', '').strip()
            admin_contact = request.form.get('admin_contact', '').strip()
            confirm_pw    = request.form.get('confirm_password', '')

            if not gp_name or not admin_name or not admin_contact or not email or not password:
                error = 'All fields are required.'
            elif password != confirm_pw:
                error = 'Passwords do not match.'
            elif len(password) < 6:
                error = 'Password must be at least 6 characters.'
            else:
                conn, c = get_db()
                try:
                    c.execute(
                        'INSERT INTO admins (gp_name, admin_name, admin_contact, admin_email, admin_password) VALUES (?, ?, ?, ?, ?)',
                        (gp_name, admin_name, admin_contact, email, password)
                    )
                    conn.commit()
                    load_gp_name()
                    session['admin_logged_in'] = True
                    session['admin_name'] = admin_name
                    session['admin_email'] = email
                    return redirect(url_for('dashboard'))
                except Exception as e:
                    error = f'Error: {str(e)}'
                finally:
                    conn.close()
        else:
            conn, c = get_db()
            c.execute('SELECT * FROM admins WHERE admin_email = ? LIMIT 1', (email,))
            admin = c.fetchone()
            conn.close()

            if admin and admin['admin_password'] == password:
                session['admin_logged_in'] = True
                session['admin_name'] = admin['admin_name']
                session['admin_email'] = admin['admin_email']
                next_page = request.args.get('next') or url_for('dashboard')
                return redirect(next_page)
            else:
                error = 'Invalid email or password. Please try again.'

    return render_template('login.html', error=error, email=email, setup_mode=setup_mode)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/add_user', methods=['POST'])
@login_required
def add_user():
    data = request.form
    insert_user(data)
    return redirect(url_for('dashboard'))


@app.route('/add_user_csv', methods=['POST'])
@login_required
def add_user_csv():
    file = request.files.get('file')
    if not file or not file.filename:
        return redirect(url_for('dashboard'))
    content = file.read().decode('utf-8-sig')
    if not content.strip():
        return redirect(url_for('dashboard'))
    reader = csv.DictReader(io.StringIO(content))
    rows = []
    for row in reader:
        normalized_row = {key: row.get(key, '') for key in fields}
        total_value = row.get('ekun_dene_rakkam', '') or row.get('ekun_dey_rakam', '')
        if not str(total_value).strip():
            total = (
                to_amount(row.get('arogya_ekun')) +
                to_amount(row.get('panipatti_ekun')) +
                to_amount(row.get('gharpatti_ekun')) +
                to_amount(row.get('divabatti_ekun'))
            )
            total_value = str(total)
        normalized_row['ekun_dene_rakkam'] = total_value
        rows.append(normalized_row)
    insert_users(rows)
    return redirect(url_for('dashboard'))


@app.route('/download_sample_csv')
@login_required
def download_sample_csv():
    return send_file(
        SAMPLE_CSV_PATH,
        mimetype='text/csv',
        as_attachment=True,
        download_name='sample_users.csv',
    )


@app.route('/edit_user/<int:sr_no>', methods=['POST'])
@login_required
def edit_user(sr_no):
    data = request.form
    conn, c = get_db()
    dict_values = [y for x,y in data.items()]
    dict_keys = [x for x,y in data.items()]
    values = tuple(dict_values)
    keys = tuple(dict_keys)
    set_clause = ', '.join([f"{key} = ?" for key in keys])
    c.execute(f'UPDATE users SET {set_clause} WHERE sr_no = ?', values + (sr_no,))
    del dict_values, dict_keys, values, keys, set_clause
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))


@app.route('/delete_user/<int:sr_no>', methods=['POST'])
@login_required
def delete_user(sr_no):
    conn, c = get_db()
    c.execute('SELECT payment_ss FROM users WHERE sr_no = ?', (sr_no,))
    user = c.fetchone()
    if user and user['payment_ss'] and os.path.exists(user['payment_ss']):
        try:
            os.remove(user['payment_ss'])
        except OSError:
            pass
    c.execute('DELETE FROM users WHERE sr_no = ?', (sr_no,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))


@app.route('/user/<int:sr_no>')
def view_user(sr_no):
    conn, c = get_db()
    c.execute('SELECT * FROM users WHERE sr_no = ?', (sr_no,))
    user = c.fetchone()
    c.execute('SELECT upi_id FROM admins LIMIT 1')
    admin = c.fetchone()
    conn.close()
    if not user:
        return "User not found", 404
    session["current_user"] = user["sr_no"]
    upi_payment_uri = build_upi_payment_uri(admin['upi_id'] if admin else None, user['ekun_dene_rakkam'])
    upi_qr_data = None
    if upi_payment_uri:
        upi_qr_data = image_buffer_to_data_url(generate_upi_qr_card_image(user, upi_payment_uri))
    service_requests = get_janam_dakhla_requests_by_user(user['sr_no'])

    return render_template(
        'view_user.html',
        user=user,
        upi_payment_uri=upi_payment_uri,
        upi_qr_data=upi_qr_data,
        service_requests=service_requests,
    )


@app.route('/services/request', methods=['POST'])
def submit_janam_dakhla_request():
    request_data = {
        'user_sr_no': session.get('current_user'),
        'service_type': request.form.get('service_type', 'birth').strip(),
        'applicant_name': request.form.get('applicant_name', '').strip(),
        'applicant_name_marathi': request.form.get('applicant_name_marathi', '').strip(),
        'applicant_name_english': request.form.get('applicant_name_english', '').strip(),
        'mobile_number': request.form.get('mobile_number', '').strip(),
        'child_name': request.form.get('child_name', '').strip(),
        'father_name': request.form.get('father_name', '').strip(),
        'mother_name': request.form.get('mother_name', '').strip(),
        'birth_date': request.form.get('birth_date', '').strip(),
        'child_gender': request.form.get('child_gender', '').strip(),
        'deceased_name': request.form.get('deceased_name', '').strip(),
        'deceased_gender': request.form.get('deceased_gender', '').strip(),
        'death_date': request.form.get('death_date', '').strip(),
        'husband_name': request.form.get('husband_name', '').strip(),
        'wife_name': request.form.get('wife_name', '').strip(),
        'marriage_date': request.form.get('marriage_date', '').strip(),
        'marriage_place': request.form.get('marriage_place', '').strip(),
        'certificate_name_marathi': request.form.get('certificate_name_marathi', '').strip(),
        'certificate_name_english': request.form.get('certificate_name_english', '').strip(),
        'family_head_marathi': request.form.get('family_head_marathi', '').strip(),
        'poverty_line_number': request.form.get('poverty_line_number', '').strip(),
        'relation_with_family_head': request.form.get('relation_with_family_head', '').strip(),
    }
    if not request_data['applicant_name']:
        request_data['applicant_name'] = request_data['applicant_name_marathi'] or request_data['applicant_name_english']
    insert_janam_dakhla_request(request_data)
    return redirect(url_for('view_user', sr_no=request_data['user_sr_no']))


@app.route('/download_qr/<int:sr_no>')
def download_qr(sr_no):
    conn, c = get_db()
    c.execute('SELECT * FROM users WHERE sr_no = ?', (sr_no,))
    user = c.fetchone()
    c.execute('SELECT upi_id FROM admins LIMIT 1')
    admin = c.fetchone()
    conn.close()
    if not user:
        return "User not found", 404
    upi_payment_uri = build_upi_payment_uri(admin['upi_id'] if admin else None, user['ekun_dene_rakkam'])
    if not upi_payment_uri:
        return "QR not configured", 404
    buffer = generate_upi_qr_card_image(user, upi_payment_uri)
    return send_file(
        buffer,
        mimetype='image/png',
        as_attachment=True,
        download_name=f"qr_{user['midkatkram']}.png",
    )


@app.route('/qr_code/<int:sr_no>')
@login_required
def qr_code(sr_no):
    conn, c = get_db()
    c.execute('SELECT * FROM users WHERE sr_no = ?', (sr_no,))
    user = c.fetchone()
    conn.close()
    if not user:
        return redirect(url_for('dashboard'))
    buffer = generate_qr_card_image(user)
    return send_file(buffer, mimetype='image/png', as_attachment=True, download_name=f'qr_{user["midkatkram"]}.png')


def cleanup_zip_folder(folder_path, zip_path):
    time.sleep(120)  # Wait 2 minutes
    try:
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)
        if os.path.exists(zip_path):
            os.remove(zip_path)
    except Exception as e:
        print(f"Cleanup error: {e}")

def process_user_for_zip(task):
    index, total, user_dict, base_url, folder_path = task
    buf = generate_qr_card_image(user_dict, base_url=base_url)
    safe_name = str(user_dict["midkatkram"]).replace('/', '_').replace('\\', '_')
    filename = f'qr_{safe_name}.png'
    filepath = os.path.join(folder_path, filename)
    with open(filepath, 'wb') as f:
        f.write(buf.getvalue())
    print(f"QR generated {index}/{total}")
    return filepath


@app.route('/generate_all_qr')
@login_required
def generate_all_qr():
    conn, c = get_db()
    c.execute('SELECT * FROM users')
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    
    req_id = str(uuid.uuid4())
    base_dir = os.path.join(os.path.dirname(__file__), "static", "allqrs")
    folder_path = os.path.join(base_dir, req_id)
    os.makedirs(folder_path, exist_ok=True)
    
    zip_path = os.path.join(base_dir, f"{req_id}.zip")

    base_url = request.host_url
    total_users = len(users)
    tasks = [(i, total_users, user, base_url, folder_path) for i, user in enumerate(users, start=1)]
    
    workers = min(os.cpu_count() * 2, 16)
    with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init) as executor:
        list(executor.map(process_user_for_zip, tasks))
        
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                zipf.write(file_path, file)
                
    threading.Thread(target=cleanup_zip_folder, args=(folder_path, zip_path), daemon=True).start()
    
    return send_file(zip_path, mimetype='application/zip', as_attachment=True, download_name='qr_codes.zip')


@app.route('/qr_card_img/<int:sr_no>')
def qr_card_img(sr_no):
    conn, c = get_db()
    c.execute('SELECT * FROM users WHERE sr_no = ?', (sr_no,))
    user = c.fetchone()
    conn.close()
    if not user:
        return "Not found", 404
    buffer = generate_qr_card_image(user)
    return send_file(buffer, mimetype='image/png')



def generate_qr_code_only(sr_no, base_url):
    """Generate only the QR code image (not the full card)"""
    if base_url:
        qr_url = f"{base_url.rstrip('/')}/user/{sr_no}"
    else:
        qr_url = url_for('view_user', sr_no=sr_no, _external=True)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='black', back_color='white').convert('RGB')

    buffer = io.BytesIO()
    qr_img.save(buffer, format='PNG')
    buffer.seek(0)
    return buffer

def process_user_for_print(data):
    index, total_users, user_dict, base_url = data

    buf = generate_qr_code_only(user_dict['sr_no'], base_url)

    b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    user_dict['qr_code_base64'] = f"data:image/png;base64,{b64}"

    print(f"QR generated {index}/{total_users}")

    return user_dict

@app.route('/print_all_qr')
@login_required
def print_all_qr():

    conn, c = get_db()
    c.execute('SELECT * FROM users')
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    base_url = request.host_url
    total_users = len(users)
    
    tasks = [
        (i, total_users, user, base_url)
        for i, user in enumerate(users, start=1)
    ]

    workers = min(os.cpu_count() * 2, 16)
    with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init) as executor:
        users_with_qrs = list(executor.map(process_user_for_print, tasks))

    return render_template(
        'print_all_qr.html',
        users=users_with_qrs,
        gp_name=GP_NAME,
        helpline_number=HELPLINE_NUMBER
    )

@app.route('/generateqr')
@login_required
def generateqr():
    return render_template('generateqr.html')


@app.route('/submit_payment_ss', methods=['POST'])
def submit_payment_ss():
    user_sr_no = session["current_user"]
    payment_ss = request.files["payment_ss"]
    locationpayment = "static/user_payments/" + str(session["current_user"]) + payment_ss.filename
    os.makedirs(os.path.dirname(locationpayment), exist_ok=True)
    payment_ss.save(locationpayment)
    conn, c = get_db()
    c.execute('UPDATE users SET payment_ss = ? WHERE sr_no = ?', (locationpayment, user_sr_no))
    conn.commit()
    conn.close()
    return redirect(url_for('view_user', sr_no=user_sr_no))


@app.route('/photo/<int:sr_no>')
def view_photo(sr_no):
    conn, c = get_db()
    c.execute('SELECT payment_ss FROM users WHERE sr_no = ?', (sr_no,))
    user = c.fetchone()
    conn.close()
    if user and user['payment_ss'] and os.path.exists(user['payment_ss']):
        return send_file(user['payment_ss'])
    return "None"


@app.route('/receipt/<int:sr_no>')
def receipt(sr_no):
    conn, c = get_db()
    c.execute('SELECT * FROM users WHERE sr_no = ?', (sr_no,))
    user = c.fetchone()
    conn.close()
    if user['payment_status'] == "Pending":
        return "Payment not approved yet"
    Indiandate = parse_receipt_date(user["payment_status"])
    return render_template('receipt.html', user=user, date=Indiandate, gp_name=GP_NAME)


@app.route('/approve/payment/<int:sr_no>')
@login_required
def approve_payment(sr_no):
    conn, c = get_db()
    date = datetime.datetime.now()
    paymentstatus = f"Paid {date.today()}"
    c.execute('UPDATE users SET payment_status = ? WHERE sr_no = ?', (paymentstatus, sr_no))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/services')
@login_required
def services():
    requests_list = get_janam_dakhla_requests()
    return render_template('services.html', requests=requests_list)


@app.route('/services/approve/<int:request_id>', methods=['POST'])
@login_required
def approve_service_request(request_id):
    approve_janam_dakhla_request(request_id)
    if request.is_json:
        return jsonify({'success': True})
    return redirect(request.referrer or url_for('services'))


@app.route('/reports')
@login_required
def reports():
    conn, c = get_db()
    c.execute('SELECT * FROM users')
    users = c.fetchall()
    conn.close()
    unpaid_users, paid_users, approved_users = [], [], []
    for row in users:
        user = dict(row)
        if user.get('payment_status') != "Pending":
            approved_users.append(user)
        elif user.get('payment_ss'):
            paid_users.append(user)
        else:
            unpaid_users.append(user)
    return render_template('reports.html',
                           unpaid_users=unpaid_users,
                           paid_users=paid_users,
                           approved_users=approved_users)


@app.route('/dashboard')
@app.route('/dashboard/<int:page>')
@login_required
def dashboard(page=1):
    return render_template('dashboard.html', initial_page=page)


@app.route('/api/users')
@login_required
def api_users():
    page  = max(1, int(request.args.get('page', 1)))
    limit = 300
    offset = (page - 1) * limit
    q = request.args.get('q', '').strip()
    conn, c = get_db()
    search_fields = [
        'sr_no', 'midkatkram', 'ghar_malkache_nav', 'gharpatti_magil', 'gharpatti_chalu', 'gharpatti_ekun',
        'divabatti_magil', 'divabatti_chalu', 'divabatti_ekun',
        'arogya_magil', 'arogya_chalu', 'arogya_ekun',
        'panipatti_magil', 'panipatti_chalu', 'panipatti_ekun', 'ekun_dene_rakkam'
    ]
    if q:
        like = f'%{q}%'
        where = ' OR '.join([f'{f} LIKE ?' for f in search_fields])
        params = [like] * len(search_fields)
        c.execute(f'SELECT COUNT(*) FROM users WHERE {where}', params)
        total = c.fetchone()[0]
        c.execute(f'SELECT * FROM users WHERE {where} LIMIT ? OFFSET ?', params + [limit, offset])
    else:
        c.execute('SELECT COUNT(*) FROM users')
        total = c.fetchone()[0]
        c.execute('SELECT * FROM users LIMIT ? OFFSET ?', (limit, offset))
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({'users': users, 'total': total, 'page': page, 'limit': limit, 'q': q})


@app.route('/delete_all_records', methods=['POST'])
@login_required
def delete_all_records():
    conn, c = get_db()
    c.execute('SELECT payment_ss FROM users WHERE payment_ss IS NOT NULL AND payment_ss != ""')
    payment_files = [row['payment_ss'] for row in c.fetchall()]
    for payment_path in payment_files:
        if payment_path and os.path.exists(payment_path):
            try:
                os.remove(payment_path)
            except OSError:
                pass
    c.execute('DELETE FROM users')
    try:
        c.execute("DELETE FROM sqlite_sequence WHERE name = 'users'")
    except Exception:
        pass
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))


@app.route('/')
def home():
    if session.get('admin_logged_in'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/admin')
@login_required
def admin_page():
    conn, c = get_db()
    c.execute('SELECT * FROM admins LIMIT 1')
    admin = c.fetchone()
    conn.close()
    return render_template('admin.html', admin=admin)


@app.route('/admin/save', methods=['POST'])
@login_required
def save_admin():
    gp_name          = request.form.get('gp_name', '').strip()
    admin_name       = request.form.get('admin_name', '').strip()
    admin_contact    = request.form.get('admin_contact', '').strip()
    admin_email      = request.form.get('admin_email', '').strip()
    upi_id           = request.form.get('upi_id', '').strip()
    helpline_number  = request.form.get('helpline_number', '').strip()
    conn, c = get_db()
    c.execute('SELECT id FROM admins LIMIT 1')
    existing = c.fetchone()
    try:
        if existing:
            c.execute(
                'UPDATE admins SET gp_name=?, admin_name=?, admin_contact=?, admin_email=?, upi_id=?, helpline_number=? WHERE id=?',
                (gp_name, admin_name, admin_contact, admin_email, upi_id, helpline_number, existing['id'])
            )
        else:
            c.execute(
                'INSERT INTO admins (gp_name, admin_name, admin_contact, admin_email, admin_password, upi_id, helpline_number) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (gp_name, admin_name, admin_contact, admin_email, 'changeme', upi_id, helpline_number)
            )
        conn.commit()
        load_gp_name()
        session['admin_name'] = admin_name
        session['admin_email'] = admin_email
        flash('Information saved successfully.', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    finally:
        conn.close()
    return redirect(url_for('admin_page'))


@app.route('/admin/reset_password', methods=['POST'])
@login_required
def reset_admin_password():
    new_password = request.form.get('new_password', '')
    confirm_pw   = request.form.get('confirm_password', '')
    if new_password != confirm_pw:
        flash('Passwords do not match.', 'error')
        return redirect(url_for('admin_page'))
    if len(new_password) < 6:
        flash('Password must be at least 6 characters.', 'error')
        return redirect(url_for('admin_page'))
    conn, c = get_db()
    c.execute('UPDATE admins SET admin_password = ? WHERE id = (SELECT id FROM admins LIMIT 1)', (new_password,))
    conn.commit()
    conn.close()
    flash('Password updated successfully.', 'success')
    return redirect(url_for('admin_page'))


if __name__ == '__main__':
    init_db()
    load_gp_name()
    app.run(host="0.0.0.0", port=APP_PORT)
