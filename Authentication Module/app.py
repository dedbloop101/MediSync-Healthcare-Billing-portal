from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from fpdf import FPDF
import sqlite3
import bcrypt
import os
import io

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Database path setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

login_attempts = {}

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, dob TEXT, 
            email TEXT UNIQUE, password BLOB, role TEXT DEFAULT 'patient')''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price REAL, stock INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT, patient_name TEXT, 
            total_amount REAL, medicine_list TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        cursor.execute("SELECT COUNT(*) FROM inventory")
        if cursor.fetchone()[0] == 0:
            medicines = [('Paracetamol', 50.0, 100), ('Amoxicillin', 120.0, 50), ('Ibuprofen', 85.0, 200)]
            cursor.executemany("INSERT INTO inventory (name, price, stock) VALUES (?, ?, ?)", medicines)
        conn.commit()

@app.route('/')
def home():
    return render_template('index.html')

# --- AUTHENTICATION ---
@app.route('/register', methods=['POST'])
def register():
    name = request.form['name']
    dob = request.form['dob']
    email = request.form['email']
    role = request.form.get('role', 'patient')
    password = request.form['password'].encode('utf-8')
    hashed = bcrypt.hashpw(password, bcrypt.gensalt())

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO users (name, dob, email, password, role) VALUES (?, ?, ?, ?, ?)",
                         (name, dob, email, hashed, role))
            conn.commit()
        return redirect(url_for('registration_success'))
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Email already registered'})

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password'].encode('utf-8')

    if login_attempts.get(email, 0) >= 3:
        return jsonify({'success': False, 'message': 'Account locked!'})

    with sqlite3.connect(DB_PATH) as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if user and bcrypt.checkpw(password, user[4]):
        login_attempts[email] = 0
        session['user'], session['role'] = user[1], user[5]
        targets = {'doctor': 'doctor_dashboard', 'admin': 'admin_dashboard', 'patient': 'patient_dashboard'}
        return jsonify({'success': True, 'redirect': url_for(targets.get(user[5], 'home'))})
    
    login_attempts[email] = login_attempts.get(email, 0) + 1
    return jsonify({'success': False, 'message': 'Invalid credentials'})

# --- DASHBOARDS ---
@app.route('/doctor/dashboard')
def doctor_dashboard():
    if session.get('role') != 'doctor': return redirect(url_for('home'))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        medicines = conn.execute("SELECT * FROM inventory").fetchall()
        patients = conn.execute("SELECT name FROM users WHERE role = 'patient'").fetchall()
        recent_bills = conn.execute("SELECT * FROM bills ORDER BY date DESC LIMIT 5").fetchall()
    return render_template('doc_dashboard.html', medicines=medicines, patients=patients, recent_bills=recent_bills)

@app.route('/patient/dashboard')
def patient_dashboard():
    if session.get('role') != 'patient': return redirect(url_for('home'))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        bills = conn.execute("SELECT * FROM bills WHERE patient_name = ? ORDER BY date DESC", (session['user'],)).fetchall()
    return render_template('patient_dashboard.html', bills=bills)

@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin': return redirect(url_for('home'))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        inventory = conn.execute("SELECT * FROM inventory").fetchall()
        bills = conn.execute("SELECT * FROM bills ORDER BY date DESC").fetchall()
        users = conn.execute("SELECT name, email, role FROM users").fetchall()
    return render_template('admin_dashboard.html', inventory=inventory, bills=bills, users=users)

# --- BILLING & PDF ---
@app.route('/submit_prescription', methods=['POST'])
def submit_prescription():
    if session.get('role') != 'doctor': return "Unauthorized", 403
    patient_name = request.form.get('patient_id')
    medicine_ids = request.form.getlist('medicine[]')
    quantities = request.form.getlist('qty[]')
    total_bill, items_prescribed = 0.0, []
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for m_id, qty in zip(medicine_ids, quantities):
            med = cursor.execute("SELECT name, price FROM inventory WHERE id = ?", (m_id,)).fetchone()
            if med:
                total_bill += (med[1] * int(qty))
                items_prescribed.append(f"{med[0]} (x{qty})")
                cursor.execute("UPDATE inventory SET stock = stock - ? WHERE id = ?", (qty, m_id))
        cursor.execute("INSERT INTO bills (patient_name, total_amount, medicine_list) VALUES (?, ?, ?)", 
                       (patient_name, total_bill, ", ".join(items_prescribed)))
        conn.commit()
    return f"<h1>Bill Generated! Total: INR {total_bill}</h1><a href='/doctor/dashboard'>Back</a>"

@app.route('/download_bill/<int:bill_id>')
def download_bill(bill_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        bill = conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 24)
    pdf.cell(200, 20, txt="MediSync Healthcare", ln=True, align='C')
    pdf.set_font("Arial", '', 12)
    pdf.cell(100, 10, txt=f"Invoice: #MS-{bill['id']}")
    pdf.cell(100, 10, txt=f"Date: {bill['date']}", ln=True, align='R')
    pdf.ln(10)
    pdf.cell(200, 10, txt=f"Patient: {bill['patient_name']}", ln=True)
    pdf.cell(140, 10, txt="Description", border=1)
    pdf.cell(50, 10, txt="Amount", border=1, ln=True)
    pdf.cell(140, 10, txt=str(bill['medicine_list']), border=1)
    pdf.cell(50, 10, txt=f"INR {bill['total_amount']}", border=1, ln=True)
    
    output = io.BytesIO()
    pdf_out = pdf.output(dest='S').encode('latin-1')
    output.write(pdf_out)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"Bill_{bill_id}.pdf", mimetype='application/pdf')

@app.route('/registration-success')
def registration_success():
    return render_template('success.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)