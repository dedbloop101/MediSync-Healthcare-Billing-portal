from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from fpdf import FPDF
import sqlite3
import bcrypt
import os
import io

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- DATABASE SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

login_attempts = {}

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # User Table: Credentials and Role-Based Access Control (RBAC)
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT, dob TEXT, email TEXT UNIQUE, 
            password BLOB, role TEXT DEFAULT 'patient')''')
        
        # Inventory Table: Real-time stock tracking
        cursor.execute('''CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            name TEXT, price REAL, stock INTEGER)''')
        
        # Billing Table: Master transaction ledger
        cursor.execute('''CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            patient_name TEXT, total_amount REAL, 
            medicine_list TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Seed Initial Inventory
        cursor.execute("SELECT COUNT(*) FROM inventory")
        if cursor.fetchone()[0] == 0:
            medicines = [
                ('Paracetamol', 50.0, 100), ('Amoxicillin', 120.0, 50), 
                ('Ibuprofen', 85.0, 200), ('Cetirizine', 40.0, 150),
                ('Azithromycin', 180.0, 30)
            ]
            cursor.executemany("INSERT INTO inventory (name, price, stock) VALUES (?, ?, ?)", medicines)
        conn.commit()

# --- AUTHENTICATION ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    name, dob, email = request.form['name'], request.form['dob'], request.form['email']
    role = request.form.get('role', 'patient')
    password = request.form['password'].encode('utf-8')
    hashed = bcrypt.hashpw(password, bcrypt.gensalt())

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO users (name, dob, email, password, role) VALUES (?, ?, ?, ?, ?)",
                         (name, dob, email, hashed, role))
            conn.commit()
        return redirect(url_for('home'))
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Email already registered'})

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password'].encode('utf-8')

    if login_attempts.get(email, 0) >= 3:
        return jsonify({'success': False, 'message': 'Account locked! Contact Admin.'})

    with sqlite3.connect(DB_PATH) as conn:
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if user and bcrypt.checkpw(password, user[4]):
        login_attempts[email] = 0 
        session['user'], session['role'] = user[1], user[5]
        targets = {'doctor': 'doctor_dashboard', 'admin': 'admin_dashboard', 'patient': 'patient_dashboard'}
        return jsonify({'success': True, 'redirect': url_for(targets.get(user[5], 'home'))})
    
    login_attempts[email] = login_attempts.get(email, 0) + 1
    return jsonify({'success': False, 'message': 'Invalid credentials'})

# --- DOCTOR PORTAL ---
@app.route('/doctor/dashboard')
def doctor_dashboard():
    if session.get('role') != 'doctor': return redirect(url_for('home'))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        medicines = conn.execute("SELECT * FROM inventory WHERE stock > 0").fetchall()
        patients = conn.execute("SELECT name FROM users WHERE role = 'patient'").fetchall()
        recent_bills = conn.execute("SELECT * FROM bills ORDER BY date DESC LIMIT 5").fetchall()
    return render_template('doc_dashboard.html', medicines=medicines, patients=patients, recent_bills=recent_bills)

@app.route('/doctor/appointments')
def doctor_appointments():
    if session.get('role') != 'doctor': return redirect(url_for('home'))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        appointments = conn.execute("SELECT * FROM bills ORDER BY date DESC").fetchall()
    return render_template('doc_appointments.html', appointments=appointments)

@app.route('/doctor/patients_list')
def doctor_patients():
    if session.get('role') != 'doctor': return redirect(url_for('home'))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        patients = conn.execute("SELECT name, email, dob FROM users WHERE role = 'patient'").fetchall()
    return render_template('doc_patients.html', patients=patients)

# --- PATIENT PORTAL ---
@app.route('/patient/dashboard')
def patient_dashboard():
    if session.get('role') != 'patient': return redirect(url_for('home'))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        bills = conn.execute("SELECT * FROM bills WHERE patient_name = ? ORDER BY date DESC", (session['user'],)).fetchall()
    return render_template('patient_dashboard.html', bills=bills)

@app.route('/patient/prescriptions')
def patient_prescriptions():
    if session.get('role') != 'patient': return redirect(url_for('home'))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        prescriptions = conn.execute("SELECT * FROM bills WHERE patient_name = ? ORDER BY date DESC", (session['user'],)).fetchall()
    return render_template('patient_prescriptions.html', prescriptions=prescriptions)

@app.route('/patient/profile')
def patient_profile():
    if session.get('role') != 'patient': return redirect(url_for('home'))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        user_data = conn.execute("SELECT name, email, dob FROM users WHERE name = ?", (session['user'],)).fetchone()
    return render_template('patient_profile.html', user=user_data)

# --- ADMIN PORTAL ---
@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin': return redirect(url_for('home'))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        inventory = conn.execute("SELECT * FROM inventory").fetchall()
        bills = conn.execute("SELECT * FROM bills ORDER BY date DESC").fetchall()
        users = conn.execute("SELECT name, email, role FROM users").fetchall()
    return render_template('admin_dashboard.html', inventory=inventory, bills=bills, users=users)

@app.route('/admin/inventory')
def admin_inventory():
    if session.get('role') != 'admin': return redirect(url_for('home'))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        inventory = conn.execute("SELECT * FROM inventory").fetchall()
    return render_template('admin_inventory.html', inventory=inventory)

@app.route('/admin/users')
def admin_users():
    if session.get('role') != 'admin': return redirect(url_for('home'))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        users = conn.execute("SELECT name, email, role FROM users").fetchall()
    return render_template('admin_users.html', users=users)

# --- PDF AUDIT & BILLING ENGINE ---
@app.route('/admin/download_full_report')
def admin_download_full_report():
    if session.get('role') != 'admin': return "Unauthorized", 403
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        bills = conn.execute("SELECT * FROM bills ORDER BY date DESC").fetchall()
        total_revenue = sum(bill['total_amount'] for bill in bills)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 20)
    pdf.set_text_color(13, 110, 253)
    pdf.cell(200, 15, txt="MediSync | Executive Audit Report", ln=True, align='C')
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(190, 10, txt=f"Financial Summary: Revenue INR {total_revenue}", border=1, ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_fill_color(13, 110, 253)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(40, 10, txt="Date", border=1, fill=True)
    pdf.cell(80, 10, txt="Patient", border=1, fill=True)
    pdf.cell(70, 10, txt="Amount (INR)", border=1, fill=True, ln=True)
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", '', 10)
    for bill in bills:
        pdf.cell(40, 10, txt=str(bill['date'][:10]), border=1)
        pdf.cell(80, 10, txt=str(bill['patient_name']), border=1)
        pdf.cell(70, 10, txt=f"{bill['total_amount']}", border=1, ln=True)

    output = io.BytesIO()
    pdf_out = pdf.output(dest='S').encode('latin-1')
    output.write(pdf_out)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="MediSync_Audit_Report.pdf", mimetype='application/pdf')

@app.route('/submit_prescription', methods=['POST'])
def submit_prescription():
    if session.get('role') != 'doctor': return "Unauthorized", 403
    patient_name = request.form.get('patient_id')
    medicine_ids, quantities = request.form.getlist('medicine[]'), request.form.getlist('qty[]')
    total_bill, items_prescribed = 0.0, []
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for m_id, qty in zip(medicine_ids, quantities):
            qty_int = int(qty)
            if qty_int <= 0: continue 
            med = cursor.execute("SELECT name, price FROM inventory WHERE id = ?", (m_id,)).fetchone()
            if med:
                total_bill += (med[1] * qty_int)
                items_prescribed.append(f"{med[0]} (x{qty_int})")
                cursor.execute("UPDATE inventory SET stock = stock - ? WHERE id = ?", (qty_int, m_id))
        if items_prescribed:
            cursor.execute("INSERT INTO bills (patient_name, total_amount, medicine_list) VALUES (?, ?, ?)", 
                           (patient_name, total_bill, ", ".join(items_prescribed)))
            conn.commit()
    return render_template('success_billing.html', total=total_bill, patient=patient_name)

@app.route('/download_bill/<int:bill_id>')
def download_bill(bill_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        bill = conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()
    if not bill: return "Bill Not Found", 404
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 24)
    pdf.set_text_color(13, 110, 253)
    pdf.cell(200, 20, txt="MediSync Healthcare", ln=True, align='C')
    pdf.set_font("Arial", '', 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(200, 10, txt=f"Invoice: #MS-{bill['id']} | Date: {bill['date']}", ln=True, align='C')
    pdf.ln(10)
    pdf.cell(140, 10, txt="Medicine List", border=1)
    pdf.cell(50, 10, txt="Total (INR)", border=1, ln=True)
    pdf.cell(140, 15, txt=str(bill['medicine_list']), border=1)
    pdf.cell(50, 15, txt=f"{bill['total_amount']}", border=1, ln=True)
    
    output = io.BytesIO()
    pdf_out = pdf.output(dest='S').encode('latin-1')
    output.write(pdf_out)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f"Invoice_{bill_id}.pdf", mimetype='application/pdf')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)