from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import sqlite3
import requests
import hashlib
import json
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your-super-secret-key-change-in-production'
@app.route('/')
def home():
    return render_template('index.html')

# Database initialization
def init_db():
    conn = sqlite3.connect('donation_platform.db')
    c = conn.cursor()
    
    # Users table (for both donors and receivers)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        user_type TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # NGOs table
    c.execute('''CREATE TABLE IF NOT EXISTS ngos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        org_name TEXT NOT NULL,
        location TEXT NOT NULL,
        contact_number TEXT NOT NULL,
        email TEXT NOT NULL,
        website TEXT,
        bank_name TEXT NOT NULL,
        account_number TEXT NOT NULL,
        upi_id TEXT,
        qr_code_path TEXT,
        niti_aayog_id TEXT NOT NULL,
        tax_certificate_path TEXT,
        is_verified BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    
    # Donations table
    c.execute('''CREATE TABLE IF NOT EXISTS donations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        donor_email TEXT NOT NULL,
        ngo_id INTEGER,
        amount REAL NOT NULL,
        payment_method TEXT NOT NULL,
        transaction_id TEXT UNIQUE NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ngo_id) REFERENCES ngos (id)
    )''')
    
    # Stories table
    c.execute('''CREATE TABLE IF NOT EXISTS stories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ngo_id INTEGER,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        image_path TEXT,
        is_approved BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ngo_id) REFERENCES ngos (id)
    )''')
    
    # Urgent requirements table
    c.execute('''CREATE TABLE IF NOT EXISTS urgent_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ngo_id INTEGER,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        amount_needed REAL NOT NULL,
        amount_raised REAL DEFAULT 0,
        deadline DATE,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (ngo_id) REFERENCES ngos (id)
    )''')
    
    # Money usage tracking
    c.execute('''CREATE TABLE IF NOT EXISTS money_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        donation_id INTEGER,
        ngo_id INTEGER,
        description TEXT NOT NULL,
        amount_used REAL NOT NULL,
        receipt_path TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (donation_id) REFERENCES donations (id),
        FOREIGN KEY (ngo_id) REFERENCES ngos (id)
    )''')
    
    conn.commit()
    conn.close()

# Create some sample data
def create_sample_data():
    conn = sqlite3.connect('donation_platform.db')
    c = conn.cursor()
    
    # Check if data already exists
    c.execute('SELECT COUNT(*) FROM users')
    if c.fetchone()[0] > 0:
        conn.close()
        return
    
    # Create sample users
    donor_password = generate_password_hash('password123')
    ngo_password = generate_password_hash('password123')
    
    c.execute('INSERT INTO users (email, password, user_type) VALUES (?, ?, ?)', 
             ('donor@example.com', donor_password, 'donor'))
    c.execute('INSERT INTO users (email, password, user_type) VALUES (?, ?, ?)', 
             ('ngo@example.com', ngo_password, 'receiver'))
    
    # Create sample NGO
    c.execute('''INSERT INTO ngos (user_id, org_name, location, contact_number, email, 
                website, bank_name, account_number, upi_id, niti_aayog_id, is_verified) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
             (2, 'Hope Foundation', 'Mumbai, Maharashtra', '+91-9876543210', 'ngo@example.com',
              'https://hopefoundation.org', 'State Bank of India', '1234567890', 'hope@upi',
              'MH/2020/0123456', True))
    
    # Create sample story
    c.execute('INSERT INTO stories (ngo_id, title, content, is_approved) VALUES (?, ?, ?, ?)',
             (1, 'Provided Clean Water to 100 Families', 
              'With the generous donations from our supporters, we were able to install 5 new water purification systems in rural villages. This initiative has provided clean drinking water to over 100 families, significantly reducing waterborne diseases in the community.', 
              True))
    
    # Create sample urgent requirement
    c.execute('''INSERT INTO urgent_requirements (ngo_id, title, description, amount_needed, amount_raised, deadline) 
                VALUES (?, ?, ?, ?, ?, ?)''',
             (1, 'Emergency Food Relief for Flood Victims', 
              'Urgent need for food supplies for 200 families affected by recent floods. We need immediate funds to purchase and distribute emergency food packets, clean water, and basic necessities.',
              50000, 15000, '2024-12-31'))
    
    conn.commit()
    conn.close()

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    conn = sqlite3.connect('donation_platform.db')
    c = conn.cursor()
    
    # Get featured stories
    c.execute('''SELECT s.title, s.content, n.org_name, s.created_at 
                FROM stories s 
                JOIN ngos n ON s.ngo_id = n.id 
                WHERE s.is_approved = TRUE 
                ORDER BY s.created_at DESC LIMIT 3''')
    stories = c.fetchall()
    
    # Get urgent requirements
    c.execute('''SELECT ur.title, ur.description, ur.amount_needed, ur.amount_raised, n.org_name 
                FROM urgent_requirements ur 
                JOIN ngos n ON ur.ngo_id = n.id 
                WHERE ur.is_active = TRUE 
                ORDER BY ur.deadline ASC LIMIT 3''')
    urgent_reqs = c.fetchall()
    
    conn.close()
    
    return render_template('index.html', stories=stories, urgent_requirements=urgent_reqs)

@app.route('/choose_role')
def choose_role():
    return render_template('choose_role.html')

@app.route('/register/<role>')
def register(role):
    if role not in ['donor', 'receiver']:
        return redirect(url_for('index'))
    return render_template('register.html', role=role)

@app.route('/process_register', methods=['POST'])
def process_register():
    email = request.form['email']
    password = request.form['password']
    user_type = request.form['user_type']
    
    # Hash password
    hashed_password = generate_password_hash(password)
    
    conn = sqlite3.connect('donation_platform.db')
    c = conn.cursor()
    
    try:
        c.execute('INSERT INTO users (email, password, user_type) VALUES (?, ?, ?)', 
                 (email, hashed_password, user_type))
        user_id = c.lastrowid
        conn.commit()
        
        session['user_id'] = user_id
        session['email'] = email
        session['user_type'] = user_type
        
        flash('Registration successful!')
        
        if user_type == 'receiver':
            return redirect(url_for('ngo_registration'))
        else:
            return redirect(url_for('donor_dashboard'))
            
    except sqlite3.IntegrityError:
        flash('Email already exists!')
        return redirect(url_for('register', role=user_type))
    finally:
        conn.close()

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/process_login', methods=['POST'])
def process_login():
    email = request.form['email']
    password = request.form['password']
    
    conn = sqlite3.connect('donation_platform.db')
    c = conn.cursor()
    c.execute('SELECT id, password, user_type FROM users WHERE email = ?', (email,))
    user = c.fetchone()
    conn.close()
    
    if user and check_password_hash(user[1], password):
        session['user_id'] = user[0]
        session['email'] = email
        session['user_type'] = user[2]
        
        flash('Login successful!')
        
        if user[2] == 'receiver':
            return redirect(url_for('ngo_dashboard'))
        else:
            return redirect(url_for('donor_dashboard'))
    else:
        flash('Invalid email or password!')
        return redirect(url_for('login'))

@app.route('/ngo_registration')
@login_required
def ngo_registration():
    if session['user_type'] != 'receiver':
        flash('Access denied!')
        return redirect(url_for('index'))
    return render_template('ngo_registration.html')

@app.route('/process_ngo_registration', methods=['POST'])
@login_required
def process_ngo_registration():
    if session['user_type'] != 'receiver':
        flash('Access denied!')
        return redirect(url_for('index'))
        
    # Get form data
    org_name = request.form['org_name']
    location = request.form['location']
    contact_number = request.form['contact_number']
    email = request.form['email']
    website = request.form.get('website', '')
    bank_name = request.form['bank_name']
    account_number = request.form['account_number']
    upi_id = request.form.get('upi_id', '')
    niti_aayog_id = request.form['niti_aayog_id']
    
    # Verify NITI Aayog ID (simplified - in real implementation, call actual API)
    is_verified = verify_niti_aayog_id(niti_aayog_id, org_name)
    
    conn = sqlite3.connect('donation_platform.db')
    c = conn.cursor()
    
    c.execute('''INSERT INTO ngos (user_id, org_name, location, contact_number, email, 
                website, bank_name, account_number, upi_id, niti_aayog_id, is_verified) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
             (session['user_id'], org_name, location, contact_number, email,
              website, bank_name, account_number, upi_id, niti_aayog_id, is_verified))
    
    conn.commit()
    conn.close()
    
    if is_verified:
        flash('NGO registered and verified successfully!')
    else:
        flash('NGO registered but verification failed. Please contact support.')
    
    return redirect(url_for('ngo_dashboard'))

def verify_niti_aayog_id(niti_id, org_name):
    """
    Simplified verification - in real implementation, this would call NITI Aayog API
    """
    # Mock verification logic
    if len(niti_id) >= 10 and niti_id.replace('/', '').replace('\\', '').isalnum():
        return True
    return False

@app.route('/donor_dashboard')
@login_required
def donor_dashboard():
    if session['user_type'] != 'donor':
        flash('Access denied!')
        return redirect(url_for('index'))
        
    conn = sqlite3.connect('donation_platform.db')
    c = conn.cursor()
    
    # Get all verified NGOs
    c.execute('''SELECT id, org_name, location, website, 
                (SELECT COUNT(*) FROM donations WHERE ngo_id = ngos.id AND status = 'completed') as donation_count
                FROM ngos WHERE is_verified = TRUE''')
    ngos = c.fetchall()
    
    conn.close()
    return render_template('donor_dashboard.html', ngos=ngos)

@app.route('/ngo_dashboard')
@login_required
def ngo_dashboard():
    if session['user_type'] != 'receiver':
        flash('Access denied!')
        return redirect(url_for('index'))
        
    conn = sqlite3.connect('donation_platform.db')
    c = conn.cursor()
    
    # Get NGO details
    c.execute('SELECT * FROM ngos WHERE user_id = ?', (session['user_id'],))
    ngo = c.fetchone()
    
    if not ngo:
        return redirect(url_for('ngo_registration'))
    
    # Get donations received
    c.execute('''SELECT donor_email, amount, created_at, status 
                FROM donations WHERE ngo_id = ? ORDER BY created_at DESC''', (ngo[0],))
    donations = c.fetchall()
    
    # Get stories count
    c.execute('SELECT COUNT(*) FROM stories WHERE ngo_id = ?', (ngo[0],))
    stories_count = c.fetchone()[0]
    
    # Get urgent requirements count  
    c.execute('SELECT COUNT(*) FROM urgent_requirements WHERE ngo_id = ? AND is_active = TRUE', (ngo[0],))
    urgent_count = c.fetchone()[0]
    
    conn.close()
    return render_template('ngo_dashboard.html', ngo=ngo, donations=donations, 
                         stories_count=stories_count, urgent_count=urgent_count)

@app.route('/ngo_details/<int:ngo_id>')
@login_required
def ngo_details(ngo_id):
    conn = sqlite3.connect('donation_platform.db')
    c = conn.cursor()
    
    c.execute('SELECT * FROM ngos WHERE id = ? AND is_verified = TRUE', (ngo_id,))
    ngo = c.fetchone()
    
    if not ngo:
        flash('NGO not found or not verified!')
        return redirect(url_for('donor_dashboard'))
    
    # Get NGO's stories
    c.execute('SELECT title, content, created_at FROM stories WHERE ngo_id = ? AND is_approved = TRUE', (ngo_id,))
    stories = c.fetchall()
    
    conn.close()
    return render_template('ngo_details.html', ngo=ngo, stories=stories)

@app.route('/donate/<int:ngo_id>')
@login_required
def donate(ngo_id):
    if session['user_type'] != 'donor':
        flash('Only donors can make donations!')
        return redirect(url_for('login'))
        
    conn = sqlite3.connect('donation_platform.db')
    c = conn.cursor()
    c.execute('SELECT * FROM ngos WHERE id = ? AND is_verified = TRUE', (ngo_id,))
    ngo = c.fetchone()
    conn.close()
    
    if not ngo:
        flash('NGO not found!')
        return redirect(url_for('donor_dashboard'))
    
    return render_template('donate.html', ngo=ngo)

@app.route('/process_donation', methods=['POST'])
@login_required
def process_donation():
    if session['user_type'] != 'donor':
        flash('Only donors can make donations!')
        return redirect(url_for('login'))
        
    ngo_id = request.form['ngo_id']
    amount = float(request.form['amount'])
    payment_method = request.form['payment_method']
    
    # Generate unique transaction ID
    transaction_id = hashlib.md5(f"{session['email']}{ngo_id}{amount}{datetime.now()}".encode()).hexdigest()
    
    conn = sqlite3.connect('donation_platform.db')
    c = conn.cursor()
    
    c.execute('''INSERT INTO donations (donor_email, ngo_id, amount, payment_method, transaction_id, status) 
                VALUES (?, ?, ?, ?, ?, ?)''',
             (session['email'], ngo_id, amount, payment_method, transaction_id, 'completed'))
    
    conn.commit()
    conn.close()
    
    flash(f'Donation of ₹{amount} completed successfully! Transaction ID: {transaction_id}')
    return redirect(url_for('donor_dashboard'))

@app.route('/add_story')
@login_required
def add_story():
    if session['user_type'] != 'receiver':
        flash('Only NGOs can add stories!')
        return redirect(url_for('index'))
    return render_template('add_story.html')

@app.route('/process_story', methods=['POST'])
@login_required
def process_story():
    if session['user_type'] != 'receiver':
        flash('Only NGOs can add stories!')
        return redirect(url_for('index'))
    
    title = request.form['title']
    content = request.form['content']
    
    conn = sqlite3.connect('donation_platform.db')
    c = conn.cursor()
    
    # Get NGO ID
    c.execute('SELECT id FROM ngos WHERE user_id = ?', (session['user_id'],))
    ngo = c.fetchone()
    
    if ngo:
        c.execute('INSERT INTO stories (ngo_id, title, content, is_approved) VALUES (?, ?, ?, ?)',
                 (ngo[0], title, content, True))  # Auto-approve for demo
        conn.commit()
        flash('Story submitted successfully!')
    else:
        flash('Please complete your NGO registration first.')
    
    conn.close()
    return redirect(url_for('ngo_dashboard'))

@app.route('/add_urgent_requirement')
@login_required
def add_urgent_requirement():
    if session['user_type'] != 'receiver':
        flash('Only NGOs can add urgent requirements!')
        return redirect(url_for('index'))
    return render_template('add_urgent_requirement.html')

@app.route('/process_urgent_requirement', methods=['POST'])
@login_required
def process_urgent_requirement():
    if session['user_type'] != 'receiver':
        flash('Only NGOs can add urgent requirements!')
        return redirect(url_for('index'))
    
    title = request.form['title']
    description = request.form['description']
    amount_needed = float(request.form['amount_needed'])
    deadline = request.form['deadline'] if request.form['deadline'] else None
    
    conn = sqlite3.connect('donation_platform.db')
    c = conn.cursor()
    
    # Get NGO ID
    c.execute('SELECT id FROM ngos WHERE user_id = ?', (session['user_id'],))
    ngo = c.fetchone()
    
    if ngo:
        c.execute('''INSERT INTO urgent_requirements (ngo_id, title, description, amount_needed, deadline) 
                    VALUES (?, ?, ?, ?, ?)''',
                 (ngo[0], title, description, amount_needed, deadline))
        conn.commit()
        flash('Urgent requirement posted successfully!')
    else:
        flash('Please complete your NGO registration first.')
    
    conn.close()
    return redirect(url_for('ngo_dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.')
    return redirect(url_for('index'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/stories')
def stories():
    conn = sqlite3.connect("donation_platform.db")
    c = conn.cursor()
    c.execute('''SELECT s.title, s.content, n.org_name, s.created_at
                 FROM stories s
                 JOIN ngos n ON s.ngo_id = n.id
                 WHERE s.is_approved = TRUE
                 ORDER BY s.created_at DESC''')
    all_stories = c.fetchall()
    conn.close()
    return render_template('stories.html', stories=all_stories)

@app.route('/urgent_requirements')
def urgent_requirements():

    conn = sqlite3.connect('donation_platform.db')
    c = conn.cursor()
    
    c.execute('''SELECT ur.id, ur.title, ur.description, ur.amount_needed, ur.amount_raised, 
                ur.deadline, n.org_name, n.id as ngo_id
                FROM urgent_requirements ur 
                JOIN ngos n ON ur.ngo_id = n.id 
                WHERE ur.is_active = TRUE 
                ORDER BY ur.deadline ASC''')
    requirements = c.fetchall()
    
    conn.close()
    return render_template('urgent_requirements.html', requirements=requirements)

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Create uploads directory
    os.makedirs('static', exist_ok=True)
    os.makedirs('static/uploads', exist_ok=True)
    
    # Initialize database
    init_db()
    
    # Create sample data
    create_sample_data()
    
    print("🚀 DonateSecure Platform Starting...")
    print("📊 Database initialized with sample data")
    print("🌐 Server running at: http://localhost:5000")
    print("💡 Demo Credentials:")
    print("   Donor: donor@example.com / password123")
    print("   NGO:   ngo@example.com / password123")
    
    # Run the app
    app.run(debug=True, host='0.0.0.0', port=5000)
