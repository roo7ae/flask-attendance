from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2
import openpyxl
import os
import pytz
import json
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ========== إنشاء قاعدة البيانات ==========
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'employee', 'supervisor'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT CHECK(type IN ('in', 'out')),
        timestamp TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')
    c.execute("SELECT * FROM users WHERE role='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (name, username, password, role) VALUES (?, ?, ?, ?)",
                  ('مدير النظام', 'admin', 'admin123', 'admin'))
    conn.commit()
    conn.close()

init_db()

# ========== تحديد الموقع الجغرافي ==========
def is_within_allowed_area(lat, lng):
    def load_location():
        try:
            with open('location.json', 'r', encoding='utf-8') as f:
                loc = json.load(f)
                return float(loc.get("lat", 0)), float(loc.get("lon", 0))
        except:
            return 0, 0

    ALLOWED_LAT, ALLOWED_LNG = load_location()
    RADIUS_METERS = 100

    def haversine(lat1, lon1, lat2, lon2):
        R = 6371000
        phi1 = radians(lat1)
        phi2 = radians(lat2)
        d_phi = radians(lat2 - lat1)
        d_lambda = radians(lon2 - lon1)
        a = sin(d_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        return R * c

    return haversine(ALLOWED_LAT, ALLOWED_LNG, lat, lng) <= RADIUS_METERS

# ========== تسجيل الدخول ==========
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            session['user_id'] = user[0]
            session['name'] = user[1]
            session['username'] = user[2]
            session['role'] = user[4]
            if user[4] == 'admin':
                return redirect('/admin')
            elif user[4] == 'supervisor':
                return redirect('/supervisor')
            else:
                return redirect('/dashboard')
        else:
            flash('❌ اسم المستخدم أو كلمة المرور غير صحيحة')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ========== لوحة الموظف ==========
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session or session['role'] not in ['employee', 'supervisor']:
        return redirect('/')
    return render_template('dashboard.html', name=session['name'])

@app.route('/attendance/<atype>', methods=['POST'])
def attendance(atype):
    if 'user_id' not in session or session['role'] not in ['employee', 'supervisor']:
        return redirect('/')
    if atype not in ['in', 'out']:
        return "نوع غير صالح", 400
    try:
        lat = float(request.form['latitude'])
        lng = float(request.form['longitude'])
    except:
        flash(⚠️ تعذر تحديد الموقع الجغرافي')
        return redirect('/dashboard')
    if not is_within_allowed_area(lat, lng):
        flash('🚫 يجب أن تكون في الموقع المحدد لتسجيل الحضور أو الانصراف')
        return redirect('/dashboard')

    local_tz = pytz.timezone('Asia/Dubai')  # توقيت دبي
    now = datetime.now(local_tz).strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO attendance (user_id, type, timestamp) VALUES (?, ?, ?)",
              (session['user_id'], atype, now))
    conn.commit()
    conn.close()
    flash(f'✅ تم تسجيل {"الحضور 🟢" if atype == "in" else "الانصراف 🔴"} بنجاح')
    return redirect('/dashboard')

# باقي الدوال كما هي في نسختك الأخيرة...

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
