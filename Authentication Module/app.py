from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import bcrypt
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

DB_PATH = 'database.db'

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            dob TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password BLOB NOT NULL,
            role TEXT DEFAULT 'patient' 
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT,
            total_amount REAL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
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
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (name, dob, email, password, role) VALUES (?, ?, ?, ?, ?)",
                           (name, dob, email, hashed, role))
            conn.commit()
            return redirect(url_for('registration_success'))
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Email already registered'})

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password'].encode('utf-8')

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()

    if user and bcrypt.checkpw(password, user[4]):
        session['user'] = user[1]
        session['role'] = user[5]
        
        # Determine redirect target based on role
        if user[5] == 'doctor':
            target = url_for('doctor_dashboard')
        elif user[5] == 'admin':
            target = url_for('admin_dashboard')
        else:
            target = url_for('patient_dashboard')
            
        return jsonify({'success': True, 'redirect': target})
    
    return jsonify({'success': False, 'message': 'Invalid credentials'})

# --- DOCTOR DASHBOARD ---
@app.route('/doctor/dashboard')
def doctor_dashboard():
    if session.get('role') != 'doctor':
        return redirect(url_for('home'))
        
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        medicines = cursor.execute("SELECT * FROM inventory").fetchall()
        patients = cursor.execute("SELECT name FROM users WHERE role = 'patient'").fetchall()
        recent_bills = cursor.execute("SELECT * FROM bills ORDER BY date DESC LIMIT 5").fetchall()
        
    return render_template('doc_dashboard.html', medicines=medicines, patients=patients, recent_bills=recent_bills)

# --- PATIENT DASHBOARD ---
@app.route('/patient/dashboard')
def patient_dashboard():
    if session.get('role') != 'patient':
        return redirect(url_for('home'))
        
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        # We fetch bills where the patient_name matches the session user name
        my_bills = conn.execute("SELECT * FROM bills WHERE patient_name = ? ORDER BY date DESC", (session['user'],)).fetchall()
        
    return render_template('patient_dashboard.html', bills=my_bills)

# --- ADMIN DASHBOARD ---
@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
        
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        inventory = conn.execute("SELECT * FROM inventory").fetchall()
        all_bills = conn.execute("SELECT * FROM bills ORDER BY date DESC").fetchall()
        all_users = conn.execute("SELECT name, email, role FROM users").fetchall()
        
    return render_template('admin_dashboard.html', inventory=inventory, bills=all_bills, users=all_users)

# --- BILLING ACTION ---
@app.route('/submit_prescription', methods=['POST'])
def submit_prescription():
    if session.get('role') != 'doctor':
        return "Unauthorized", 403

    patient_name = request.form.get('patient_id')
    medicine_ids = request.form.getlist('medicine[]')
    quantities = request.form.getlist('qty[]')
    
    total_bill = 0.0
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for m_id, qty in zip(medicine_ids, quantities):
            cursor.execute("SELECT price FROM inventory WHERE id = ?", (m_id,))
            price = cursor.fetchone()[0]
            total_bill += (price * int(qty))
            cursor.execute("UPDATE inventory SET stock = stock - ? WHERE id = ?", (qty, m_id))
        
        cursor.execute("INSERT INTO bills (patient_name, total_amount) VALUES (?, ?)", (patient_name, total_bill))
        conn.commit()
        
    return f"<h1>Bill Generated! Total: ₹{total_bill}</h1><a href='/doctor/dashboard'>Back to Dashboard</a>"

# --- UTILITY ROUTES ---
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