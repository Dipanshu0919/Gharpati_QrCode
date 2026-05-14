import base64
import csv
import datetime
import io
import os
import qrcode
import sqlite3
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, render_template, request, redirect, url_for, send_file, session, flash

app = Flask(__name__)
app.secret_key = "replace-with-a-secure-key"
app.config['SESSION_PERMANENT'] = False
DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")
UPI_QR_FILENAME = "upiqr.png"

GP_NAME = "ग्रामपंचायत"

def load_gp_name():
    global GP_NAME
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT gp_name FROM admins LIMIT 1')
        row = c.fetchone()
        conn.close()
        if row and row['gp_name']:
            GP_NAME = row['gp_name']
    except Exception:
        pass

fields = {
    "midkatkram": "मिळकत क्र",
    "malkachenaab": "मालकाचे नाव",
    "gharpati_magil": "घरपट्टी (मागील)",
    "gharpati_chalu": "घरपट्टी (चालू)",
    "gharpati_akun": "घरपट्टी (एकूण)",
    "divabatti_magil": "दिवाबत्ती (मागील)",
    "divabatti_chalu": "दिवाबत्ती (चालू)",
    "divabatti_akun": "दिवाबत्ती (एकूण)",
    "arogya_magil": "आरोग्य (मागील)",
    "arogya_chalu": "आरोग्य (चालू)",
    "arogya_akun": "आरोग्य (एकूण)",
    "panipati_magil": "पाणीपट्टी (मागील)",
    "panipati_chalu": "पाणीपट्टी (चालू)",
    "panipati_akun": "पाणीपट्टी (एकूण)",
    "akud_dey_rakam": "एकूण येणे रक्कम",
}

@app.context_processor
def inject_globals():
    upi_qr_path = os.path.join(app.static_folder, UPI_QR_FILENAME)
    return {
        "fields": fields,
        "gp_name": GP_NAME,
        "upi_qr_filename": UPI_QR_FILENAME,
        "upi_qr_exists": os.path.exists(upi_qr_path),
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
            malkachenaab TEXT,
            gharpati_magil TEXT,
            gharpati_chalu TEXT,
            gharpati_akun TEXT,
            divabatti_magil TEXT,
            divabatti_chalu TEXT,
            divabatti_akun TEXT,
            arogya_magil TEXT,
            arogya_chalu TEXT,
            arogya_akun TEXT,
            panipati_magil TEXT,
            panipati_chalu TEXT,
            panipati_akun TEXT,
            akud_dey_rakam TEXT,
            payment_ss TEXT DEFAULT NULL,
            payment_status TEXT DEFAULT "Pending"
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gp_name TEXT NOT NULL,
            admin_name TEXT NOT NULL,
            admin_contact TEXT NOT NULL,
            admin_email TEXT NOT NULL UNIQUE,
            admin_password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

def has_marathi(text):
    return bool(re.search(r'[\u0900-\u097F]', str(text)))

def get_font(size=24, text=None):
    if text is not None and not has_marathi(text):
        font_files = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        ]
    else:
        font_files = [
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    for path in font_files:
        try:
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

def draw_fitted_text(draw, text, box, fill, max_size=28, min_size=14, align='left'):
    x0, y0, x1, y1 = box
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    chosen_size = min_size
    chosen_width = 0
    for size in range(max_size, min_size - 1, -1):
        text_width = get_multilingual_text_width(draw, text, size)
        if text_width <= width:
            chosen_size = size
            chosen_width = text_width
            break
    else:
        chosen_width = get_multilingual_text_width(draw, text, min_size)
    font_y = y0 + max(0, (height - chosen_size) // 2)
    if align == 'center':
        font_x = x0 + max(0, (width - chosen_width) // 2)
    elif align == 'right':
        font_x = x1 - chosen_width
    else:
        font_x = x0
    draw_multilingual_text(draw, font_x, font_y, text, fill, chosen_size)

def parse_receipt_date(payment_status):
    if not payment_status or payment_status == "Pending":
        return None
    try:
        raw_date = payment_status.split(" ", 1)[1]
        return datetime.datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d %B %Y (%d-%m-%Y)")
    except Exception:
        return payment_status

def build_receipt_pdf(user, date_text):
    user_dict = dict(user)
    page_width = 1240
    page_height = 1754
    margin = 70
    card_left = margin
    card_top = 70
    card_right = page_width - margin
    card_bottom = page_height - margin
    card_width = card_right - card_left

    background = Image.new('RGB', (page_width, page_height), '#f0f4f8')
    draw = ImageDraw.Draw(background)

    draw.rounded_rectangle(
        [card_left, card_top, card_right, card_bottom],
        radius=24,
        fill='#ffffff',
        outline='#dbe3ee',
        width=3,
    )
    draw.rectangle([card_left, card_top, card_right, card_top + 10], fill='#1e3a8a')
    draw_fitted_text(draw, 'PAID SUCCESS', (260, 760, 980, 1180), fill=(5, 150, 105, 18), max_size=92, min_size=72, align='center')

    inner_left = card_left + 48
    inner_right = card_right - 48
    y = card_top + 38

    draw_fitted_text(draw, GP_NAME, (inner_left, y, inner_right, y + 54), '#0f172a', max_size=34, min_size=24, align='center')
    y += 52
    draw_fitted_text(draw, 'ग्रामपंचायत कार्यालय', (inner_left, y, inner_right, y + 52), '#000000', max_size=30, min_size=20, align='center')
    y += 42
    draw_fitted_text(draw, 'कर भरणा पावती (Tax Payment Receipt)', (inner_left, y, inner_right, y + 44), '#475569', max_size=22, min_size=16, align='center')

    y = card_top + 220
    meta_height = 110
    meta_bg = '#eff6ff'
    meta_left = inner_left
    meta_right = inner_right
    draw.rounded_rectangle([meta_left, y, meta_right, y + meta_height], radius=16, fill=meta_bg)
    mid = meta_left + (meta_right - meta_left) // 2
    draw.line([mid, y + 18, mid, y + meta_height - 18], fill='#d6e2f2', width=2)
    draw_fitted_text(draw, 'दिनांक (Date)', (meta_left + 22, y + 18, mid - 22, y + 48), '#64748b', max_size=16, min_size=14, align='left')
    draw_fitted_text(draw, date_text or '-', (meta_left + 22, y + 52, mid - 22, y + 92), '#1e3a8a', max_size=20, min_size=16, align='left')
    draw_fitted_text(draw, 'स्थिती (Status)', (mid + 22, y + 18, meta_right - 22, y + 48), '#64748b', max_size=16, min_size=14, align='left')
    draw_fitted_text(draw, 'Paid', (mid + 22, y + 52, meta_right - 22, y + 92), '#059669', max_size=20, min_size=16, align='left')

    y = y + meta_height + 34
    draw_fitted_text(draw, 'मालमत्ता व धारकाचा तपशील', (inner_left, y, inner_right, y + 40), '#0f172a', max_size=20, min_size=16, align='left')
    y += 52
    info_height = 112
    info_width = (meta_right - meta_left - 16) // 2
    info_gap = 16
    info_boxes = [
        (meta_left, y, meta_left + info_width, y + info_height),
        (meta_left + info_width + info_gap, y, meta_right, y + info_height),
    ]
    info_labels = [
        ('मालकाचे नाव (Owner Name)', user_dict.get('malkachenaab') or '-'),
        ('मिळकत क्रमांक (Property ID)', user_dict.get('midkatkram') or '-'),
    ]
    for box, (label, value) in zip(info_boxes, info_labels):
        x0, y0, x1, y1 = box
        draw.rounded_rectangle(box, radius=14, fill='#f8fbff', outline='#dbe3ee', width=2)
        draw_fitted_text(draw, label, (x0 + 18, y0 + 14, x1 - 18, y0 + 42), '#64748b', max_size=15, min_size=13, align='left')
        draw_fitted_text(draw, value, (x0 + 18, y0 + 48, x1 - 18, y1 - 14), '#111827', max_size=24, min_size=16, align='left')

    y = y + info_height + 34
    draw_fitted_text(draw, 'कराचा तपशील (Tax Breakdown)', (inner_left, y, inner_right, y + 40), '#0f172a', max_size=20, min_size=16, align='left')
    y += 52
    table_top = y
    row_height = 76
    col_widths = [card_width * 0.40, card_width * 0.20, card_width * 0.20, card_width * 0.20]
    table_left = inner_left
    table_right = inner_right
    table_width = table_right - table_left
    col_positions = [table_left]
    for width in col_widths:
        col_positions.append(col_positions[-1] + width)

    header_h = 72
    draw.rounded_rectangle([table_left, table_top, table_right, table_top + header_h + row_height * 5], radius=14, fill='#ffffff', outline='#d6dbe3', width=2)
    draw.rectangle([table_left, table_top, table_right, table_top + header_h], fill='#2f5f9a')
    headers = [
        'कराचा प्रकार (Tax Type)',
        'मागील थकबाकी (Arrears)',
        'चालू मागणी (Current)',
        'एकूण (Total)',
    ]
    for idx, header in enumerate(headers):
        x0 = col_positions[idx]
        x1 = col_positions[idx + 1]
        draw.line([x1, table_top, x1, table_top + header_h + row_height * 5], fill='#d6dbe3', width=2)
        draw_fitted_text(draw, header, (x0 + 10, table_top + 12, x1 - 10, table_top + header_h - 12), '#ffffff', max_size=17, min_size=13, align='center')
    draw.line([table_left, table_top + header_h, table_right, table_top + header_h], fill='#d6dbe3', width=2)

    rows = [
        ('घरपट्टी (House Tax)', user_dict.get('gharpati_magil') or '0', user_dict.get('gharpati_chalu') or '0', user_dict.get('gharpati_akun') or '0'),
        ('दिवाबत्ती (Lighting Tax)', user_dict.get('divabatti_magil') or '0', user_dict.get('divabatti_chalu') or '0', user_dict.get('divabatti_akun') or '0'),
        ('आरोग्य कर (Health Tax)', user_dict.get('arogya_magil') or '0', user_dict.get('arogya_chalu') or '0', user_dict.get('arogya_akun') or '0'),
        ('पाणीपट्टी (Water Tax)', user_dict.get('panipati_magil') or '0', user_dict.get('panipati_chalu') or '0', user_dict.get('panipati_akun') or '0'),
    ]
    for row_index, row in enumerate(rows):
        top = table_top + header_h + row_index * row_height
        bottom = top + row_height
        if row_index % 2 == 0:
            draw.rectangle([table_left, top, table_right, bottom], fill='#f8fafc')
        draw.line([table_left, bottom, table_right, bottom], fill='#d6dbe3', width=2)
        draw_fitted_text(draw, row[0], (col_positions[0] + 12, top + 12, col_positions[1] - 12, bottom - 12), '#111827', max_size=18, min_size=14, align='left')
        draw_fitted_text(draw, f'₹ {row[1]}', (col_positions[1] + 12, top + 12, col_positions[2] - 12, bottom - 12), '#111827', max_size=18, min_size=14, align='center')
        draw_fitted_text(draw, f'₹ {row[2]}', (col_positions[2] + 12, top + 12, col_positions[3] - 12, bottom - 12), '#111827', max_size=18, min_size=14, align='center')
        draw_fitted_text(draw, f'₹ {row[3]}', (col_positions[3] + 12, top + 12, col_positions[4] - 12, bottom - 12), '#111827', max_size=18, min_size=14, align='center')

    total_top = table_top + header_h + len(rows) * row_height
    total_bottom = total_top + row_height
    draw.rectangle([table_left, total_top, table_right, total_bottom], fill='#ecfdf5')
    draw.line([table_left, total_top, table_right, total_top], fill='#d6e7dc', width=2)
    draw.line([table_left, total_bottom, table_right, total_bottom], fill='#d6e7dc', width=2)
    draw_fitted_text(draw, 'एकूण भरलेली रक्कम (Total Amount Paid)', (col_positions[0] + 12, total_top + 12, col_positions[3] - 12, total_bottom - 12), '#065f46', max_size=18, min_size=14, align='left')
    draw_fitted_text(draw, f"₹ {user_dict.get('akud_dey_rakam') or '0'}", (col_positions[3] + 12, total_top + 12, col_positions[4] - 12, total_bottom - 12), '#065f46', max_size=20, min_size=16, align='center')

    footer_y = total_bottom + 42
    draw_fitted_text(draw, 'सदर पावती संगणकीकृत असल्याने त्यावर स्वाक्षरीची आवश्यकता नाही.', (inner_left, footer_y, inner_right, footer_y + 28), '#475569', max_size=17, min_size=13, align='center')
    draw_fitted_text(draw, 'This is a system generated receipt and does not require a physical signature.', (inner_left, footer_y + 34, inner_right, footer_y + 62), '#475569', max_size=15, min_size=12, align='center')
    draw_fitted_text(draw, 'कर वेळेत भरल्याबद्दल धन्यवाद! आपला कर, गावाचा विकास.', (inner_left, footer_y + 84, inner_right, footer_y + 124), '#1e3a8a', max_size=18, min_size=14, align='center')

    buffer = io.BytesIO()
    background.save(buffer, format='PDF', resolution=150.0)
    buffer.seek(0)
    return buffer

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
    qr_img = qr_img.resize((300, 300), Image.Resampling.LANCZOS)

    width = 900
    height = 750
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
        ('मालकाचे नाव', user['malkachenaab'] or '-'),
        ('मालमत्ता क्र.', user['midkatkram'] or '-'),
    ]

    for index, (title, value) in enumerate(entries):
        draw_multilingual_text(draw, detail_x, detail_y, f'{title} :', '#64748b', 24)
        draw_multilingual_text(draw, detail_x, detail_y + 35, str(value), '#0f172a', 32)
        detail_y += 100

    inst_x = 50
    inst_y = 450

    draw.rectangle([30, inst_y - 20, width - 30, inst_y + 200], fill='#fff7ed', outline='#fed7aa', width=2)

    inst_title = "घरपट्टीची रक्कम QR कोडद्वारे भरण्याचे टप्पे :"
    draw_multilingual_text(draw, inst_x, inst_y - 5, inst_title, '#c2410c', 24)

    steps = [
        "- QR कोड स्कॅन करण्यासाठी Play Store किंवा App Store वरून कोणतेही ",
        "  \"QR Code Scanner\" App डाउनलोड करा आणि उघडा आणि वरील QR कोड स्कॅन करा.",
        "- स्कॅन केल्यावर आपल्याला एक लिंक दिसेल, त्यावर क्लिक करा.",
        "- उपलब्ध UPI QR कोड स्कॅन करा आणि घरपट्टी ची रक्कम भरा !.",
    ]

    step_y = inst_y + 40
    for step in steps:
        draw_multilingual_text(draw, inst_x, step_y, step, '#431407', 22)
        step_y += 35

    draw.line([0, height - 60, width, height - 60], fill='#e2e8f0', width=2)

    footer_text = 'वेळेत कर भरा आणि गावचा विकास साधा'
    footer_w = get_multilingual_text_width(draw, footer_text, 24)
    draw_multilingual_text(draw, (width - footer_w) // 2, height - 42, footer_text, '#1e3a8a', 24)

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
    rows = [{key: row.get(key, '') for key in fields} for row in reader]
    insert_users(rows)
    return redirect(url_for('dashboard'))


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
    c.execute('DELETE FROM users WHERE sr_no = ?', (sr_no,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))


@app.route('/user/<int:sr_no>')
def view_user(sr_no):
    conn, c = get_db()
    c.execute('SELECT * FROM users WHERE sr_no = ?', (sr_no,))
    user = c.fetchone()
    conn.close()
    if not user:
        return "User not found", 404
    session["current_user"] = user["sr_no"]
    return render_template('view_user.html', user=user)


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


@app.route('/generate_all_qr')
@login_required
def generate_all_qr():
    conn, c = get_db()
    c.execute('SELECT * FROM users')
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    base_url = request.host_url
    output = io.BytesIO()
    zipf = zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED)
    def process_user(user_dict):
        buf = generate_qr_card_image(user_dict, base_url=base_url)
        return user_dict["midkatkram"], buf.getvalue()
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = executor.map(process_user, users)
        for midkatkram, img_data in results:
            zipf.writestr(f'qr_{midkatkram}.png', img_data)
    zipf.close()
    output.seek(0)
    return send_file(output, mimetype='application/zip', as_attachment=True, download_name='qr_codes.zip')


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


@app.route('/print_all_qr')
@login_required
def print_all_qr():
    conn, c = get_db()
    c.execute('SELECT * FROM users')
    users = [dict(row) for row in c.fetchall()]
    conn.close()
    base_url = request.host_url
    def process_user_for_print(user_dict):
        buf = generate_qr_card_image(user_dict, base_url=base_url)
        b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        user_dict['base64_img'] = f"data:image/png;base64,{b64}"
        return user_dict
    with ThreadPoolExecutor(max_workers=8) as executor:
        users_with_imgs = list(executor.map(process_user_for_print, users))
    return render_template('print_all_qr.html', users=users_with_imgs)


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
@login_required
def receipt(sr_no):
    conn, c = get_db()
    c.execute('SELECT * FROM users WHERE sr_no = ?', (sr_no,))
    user = c.fetchone()
    conn.close()
    if user['payment_status'] == "Pending":
        return "Payment not approved yet"
    Indiandate = parse_receipt_date(user["payment_status"])
    return render_template('receipt.html', user=user, date=Indiandate, gp_name=GP_NAME)


@app.route('/receipt/<int:sr_no>/download')
@login_required
def download_receipt_pdf(sr_no):
    conn, c = get_db()
    c.execute('SELECT * FROM users WHERE sr_no = ?', (sr_no,))
    user = c.fetchone()
    conn.close()
    if not user:
        return "Receipt not found", 404
    if user['payment_status'] == "Pending":
        return "Payment not approved yet"

    Indiandate = parse_receipt_date(user["payment_status"])
    pdf_buffer = build_receipt_pdf(user, Indiandate)
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"receipt_{sr_no}.pdf",
    )


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
@login_required
def dashboard():
    conn, c = get_db()
    c.execute('SELECT * FROM users')
    users = c.fetchall()
    conn.close()
    if not users:
        return render_template('dashboard.html', users=None)
    return render_template('dashboard.html', users=users)


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
    gp_name       = request.form.get('gp_name', '').strip()
    admin_name    = request.form.get('admin_name', '').strip()
    admin_contact = request.form.get('admin_contact', '').strip()
    admin_email   = request.form.get('admin_email', '').strip()
    upi_qr_file   = request.files.get('upi_qr')
    conn, c = get_db()
    c.execute('SELECT id FROM admins LIMIT 1')
    existing = c.fetchone()
    try:
        if existing:
            c.execute(
                'UPDATE admins SET gp_name=?, admin_name=?, admin_contact=?, admin_email=? WHERE id=?',
                (gp_name, admin_name, admin_contact, admin_email, existing['id'])
            )
        else:
            c.execute(
                'INSERT INTO admins (gp_name, admin_name, admin_contact, admin_email, admin_password) VALUES (?, ?, ?, ?, ?)',
                (gp_name, admin_name, admin_contact, admin_email, 'changeme')
            )
        if upi_qr_file and upi_qr_file.filename:
            qr_path = os.path.join(app.static_folder, UPI_QR_FILENAME)
            os.makedirs(app.static_folder, exist_ok=True)
            with Image.open(upi_qr_file.stream) as qr_image:
                qr_image.convert('RGBA').save(qr_path, format='PNG')
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
    app.run(debug=True)
