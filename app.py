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

# ========== قاعدة البيانات ==========
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
        a = sin(d_phi / 2)**2 + cos(phi1) * cos(phi2) * sin(d_lambda / 2)**2
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

# ========== لوحة الموظف والمشرف ==========
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session or session['role'] not in ['employee', 'supervisor']:
        return redirect('/')
    return render_template('dashboard.html', name=session['name'])

@app.route('/attendance/<atype>', methods=['POST'])
def attendance(atype):
    if 'user_id' not in session or session['role'] not in ['employee', 'supervisor']:
        return redirect('/')
    try:
        lat = float(request.form['latitude'])
        lng = float(request.form['longitude'])
    except:
        flash('⚠️ تعذر تحديد الموقع الجغرافي')
        return redirect('/dashboard')
    if not is_within_allowed_area(lat, lng):
        flash('🚫 يجب أن تكون في الموقع المحدد لتسجيل الحضور أو الانصراف')
        return redirect('/dashboard')
    now = datetime.now(pytz.timezone('Asia/Dubai')).strftime('%Y-%m-%d %H:%M:%S')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT INTO attendance (user_id, type, timestamp) VALUES (?, ?, ?)",
              (session['user_id'], atype, now))
    conn.commit()
    conn.close()
    flash(f'✅ تم تسجيل {"الحضور 🟢" if atype == "in" else "الانصراف 🔴"} بنجاح')
    return redirect('/dashboard')

@app.route('/my_attendance')
def my_attendance():
    if 'user_id' not in session:
        return redirect('/')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT type, timestamp FROM attendance WHERE user_id=? ORDER BY timestamp DESC", (session['user_id'],))
    records = c.fetchall()
    conn.close()
    return render_template('attendance.html', records=records)

# ========== المدير ==========
@app.route('/admin')
def admin():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    employees = c.fetchall()
    conn.close()
    return render_template('admin.html', employees=employees)

@app.route('/add_employee', methods=['GET', 'POST'])
def add_employee():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/')
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'employee')  # يدعم تحديد نوع الدور

        if not name or not username or not password:
            flash('⚠️ جميع الحقول مطلوبة')
            return redirect('/add_employee')

        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (name, username, password, role) VALUES (?, ?, ?, ?)",
                      (name, username, password, role))
            conn.commit()
            flash('✅ تمت إضافة الموظف بنجاح')
            return redirect('/admin')
        except sqlite3.IntegrityError:
            flash('⚠️ اسم المستخدم موجود بالفعل')
        finally:
            conn.close()
    return render_template('employee_form.html', action='add')

@app.route('/promote/<int:user_id>')
def promote_to_supervisor(user_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("UPDATE users SET role='supervisor' WHERE id=? AND role='employee'", (user_id,))
    conn.commit()
    conn.close()
    
    flash('✅ تم ترقية الموظف إلى مشرف')
    return redirect('/admin')

@app.route('/demote/<int:user_id>')
def demote_to_employee(user_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("UPDATE users SET role='employee' WHERE id=? AND role='supervisor'", (user_id,))
    conn.commit()
    conn.close()
    
    flash('✅ تم تحويل المشرف إلى موظف')
    return redirect('/admin')
@app.route('/delete_employee/<int:user_id>')
def delete_employee(user_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/')
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=? AND role!='admin'", (user_id,))
    conn.commit()
    conn.close()

    flash('🗑️ تم حذف الموظف أو المشرف بنجاح')
    return redirect('/admin')

@app.route('/edit_employee/<int:user_id>', methods=['GET', 'POST'])
def edit_employee(user_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    if request.method == 'POST':
        name = request.form['name']
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        c.execute("UPDATE users SET name=?, username=?, password=?, role=? WHERE id=?",
                  (name, username, password, role, user_id))
        conn.commit()
        conn.close()
        flash('✅ تم تعديل بيانات الموظف')
        return redirect('/admin')
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    employee = c.fetchone()
    conn.close()
    return render_template('employee_form.html', action='edit', employee=employee)

@app.route('/upload_users', methods=['GET', 'POST'])
def upload_users():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/')
    message = ""
    if request.method == 'POST':
        file = request.files.get('file')
        if file and file.filename.endswith('.xlsx'):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
            file.save(filepath)
            wb = openpyxl.load_workbook(filepath)
            sheet = wb.active
            added = 0
            skipped = 0
            conn = sqlite3.connect('database.db')
            c = conn.cursor()
            for i, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                if row is None or len(row) < 3:
                    skipped += 1
                    continue
                name, username, password = row[:3]
                if not all([name, username, password]):
                    skipped += 1
                    continue
                try:
                    c.execute("INSERT INTO users (name, username, password, role) VALUES (?, ?, ?, 'employee')",
                              (name.strip(), username.strip(), str(password).strip()))
                    added += 1
                except sqlite3.IntegrityError:
                    skipped += 1
            conn.commit()
            conn.close()
            message = f"✅ تم إضافة {added} موظف. ❗ تم تجاهل {skipped} صف (مكرر أو ناقص)."
        else:
            message = "⚠️ الرجاء رفع ملف Excel بصيغة .xlsx فقط"
    return render_template('upload_users.html', message=message)

@app.route('/admin/location', methods=['GET', 'POST'])
def edit_location():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect('/')
    message = ""
    try:
        with open('location.json', 'r', encoding='utf-8') as f:
            loc = json.load(f)
            lat = loc.get("lat", "")
            lon = loc.get("lon", "")
    except:
        lat = lon = ""
    if request.method == 'POST':
        lat = request.form.get('lat')
        lon = request.form.get('lon')
        try:
            float(lat)
            float(lon)
            with open('location.json', 'w', encoding='utf-8') as f:
                json.dump({'lat': lat, 'lon': lon}, f)
            message = "✅ تم تحديث الموقع بنجاح"
        except:
            message = "⚠️ يرجى إدخال قيم صحيحة"
    return render_template('edit_location.html', lat=lat, lon=lon, message=message)

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        return redirect('/')
    message = ""
    if request.method == 'POST':
        current_pw = request.form['current_password']
        new_pw = request.form['new_password']
        confirm_pw = request.form['confirm_password']
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT password FROM users WHERE id=?", (session['user_id'],))
        stored_pw = c.fetchone()[0]
        if current_pw != stored_pw:
            message = "❌ كلمة المرور الحالية غير صحيحة"
        elif new_pw != confirm_pw:
            message = "⚠️ كلمة المرور الجديدة وتأكيدها غير متطابقتين"
        else:
            c.execute("UPDATE users SET password=? WHERE id=?", (new_pw, session['user_id']))
            conn.commit()
            message = "✅ تم تغيير كلمة المرور بنجاح"
        conn.close()
    return render_template('change_password.html', message=message)

@app.route('/supervisor')
def supervisor_dashboard():
    if 'user_id' not in session or session['role'] != 'supervisor':
        return redirect('/')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE role='employee'")
    employees = c.fetchall()
    conn.close()
    return render_template('supervisor.html', employees=employees)

@app.route('/admin/attendance', methods=['GET', 'POST'])
@app.route('/supervisor/attendance', methods=['GET', 'POST'])
def view_attendance():
    if 'user_id' not in session or session['role'] not in ['admin', 'supervisor']:
        return redirect('/')
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    query = '''SELECT a.id, u.name, a.type, a.timestamp FROM attendance a JOIN users u ON a.user_id = u.id WHERE 1=1'''
    params = []
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        if user_id and user_id != "all":
            query += " AND u.id = ?"
            params.append(user_id)
        if start_date:
            query += " AND DATE(a.timestamp) >= DATE(?)"
            params.append(start_date)
        if end_date:
            query += " AND DATE(a.timestamp) <= DATE(?)"
            params.append(end_date)
    query += " ORDER BY a.timestamp DESC"
    c.execute(query, params)
    records = c.fetchall()
    c.execute("SELECT id, name FROM users WHERE role = 'employee'")
    employees = c.fetchall()
    conn.close()
    return render_template('attendance.html', records=records, employees=employees)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')