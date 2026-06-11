from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from enhanced_auth import EnhancedAuthDB, UserRole
import re
import logging
from datetime import datetime, timedelta
import requests

# Configure logging
logger = logging.getLogger(__name__)

# Create Blueprint
enhanced_auth_bp = Blueprint('enhanced_auth', __name__, url_prefix='/enhanced')

# Initialize database
enhanced_db = EnhancedAuthDB()

# Google OAuth2 Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid_configuration"

@enhanced_auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('enhanced_auth.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember_me = request.form.get('remember_me') == 'on'
        
        logger.info(f"Login attempt from form: {username}")
        
        if not username or not password:
            logger.warning(f"Login failed - missing credentials: {username}")
            flash('Please enter both username/email and password', 'error')
            return render_template('enhanced_auth/login.html')
        
        user = enhanced_db.authenticate_user(username, password)
        
        if user:
            logger.info(f"Login successful for user: {user.username}")
            login_user(user, remember=remember_me, duration=timedelta(days=30) if remember_me else None)
            # Store success message in session for dashboard display
            session['login_success'] = f'Welcome back, {user.full_name or user.username}!'
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('enhanced_auth.dashboard'))
        else:
            logger.warning(f"Login failed - invalid credentials: {username}")
            flash('Invalid username/email or password', 'error')
    
    return render_template('enhanced_auth/login.html')

@enhanced_auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('enhanced_auth.dashboard'))
    
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        account_type = request.form.get('account_type', '').strip()
        
        # Enhanced validation
        errors = []
        
        # Validate account type
        if account_type not in ['doctor', 'patient']:
            errors.append('Please select a valid account type')
        
        role = account_type if account_type in ['doctor', 'patient'] else UserRole.PATIENT.value
        
        if not full_name or len(full_name) < 2:
            errors.append('Full name must be at least 2 characters')
        
        if not email or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
            errors.append('Please enter a valid email address')
        
        if enhanced_db.email_exists(email):
            errors.append('Email address is already registered')
        
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters')
        elif not re.match(r'^[a-zA-Z0-9_]+$', username):
            errors.append('Username can only contain letters, numbers, and underscores')
        elif enhanced_db.user_exists(username):
            errors.append('Username is already taken')
        
        if not password or len(password) < 8:
            errors.append('Password must be at least 8 characters')
        
        # Enhanced password strength validation
        if password:
            strength_score = 0
            if len(password) >= 8: strength_score += 20
            if len(password) >= 12: strength_score += 10
            if re.search(r'[a-z]', password): strength_score += 20
            if re.search(r'[A-Z]', password): strength_score += 20
            if re.search(r'[0-9]', password): strength_score += 15
            if re.search(r'[^A-Za-z0-9]', password): strength_score += 15
            
            if strength_score < 40:
                errors.append('Password is too weak. Please include uppercase, lowercase, numbers, and special characters')
        
        if password != confirm_password:
            errors.append('Passwords do not match')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('enhanced_auth/signup.html')
        
        try:
            logger.info(f"Signup attempt: {username} ({email})")
            user_id = enhanced_db.create_user(username, email, full_name, password, role)
            logger.info(f"Signup successful: {username} (ID: {user_id})")
            flash('Account created successfully. Please log in.', 'success')
            return redirect(url_for('enhanced_auth.login'))
            
        except ValueError as e:
            logger.error(f"Signup failed for {username}: {e}")
            flash(str(e), 'error')
        except Exception as e:
            logger.error(f"Unexpected signup error for {username}: {e}")
            flash('An error occurred while creating your account. Please try again.', 'error')
    
    return render_template('enhanced_auth/signup.html')

@enhanced_auth_bp.route('/google-login')
def google_login():
    # Check if Google OAuth is configured
    if not GOOGLE_CLIENT_ID or GOOGLE_CLIENT_ID == 'your-google-client-id':
        flash('Google OAuth is not configured. Please contact administrator.', 'error')
        return redirect(url_for('enhanced_auth.login'))
    
    # Simplified Google OAuth2 authorization URL (without state for now)
    google_auth_url = (
        f"https://accounts.google.com/o/oauth2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri=http://localhost:8000/enhanced/google-callback&"
        f"scope=openid email profile&"
        f"response_type=code"
    )
    
    return redirect(google_auth_url)

@enhanced_auth_bp.route('/google-callback')
def google_callback():
    # Skip state verification for now (can be re-enabled later)
    # if request.args.get('state') != session.get('oauth_state'):
    #     flash('Invalid state parameter', 'error')
    #     return redirect(url_for('enhanced_auth.login'))
    
    code = request.args.get('code')
    if not code:
        flash('Google authentication failed', 'error')
        return redirect(url_for('enhanced_auth.login'))
    
    try:
        # Exchange code for token
        token_data = {
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': "http://localhost:8000/enhanced/google-callback"
        }
        
        token_response = requests.post('https://oauth2.googleapis.com/token', data=token_data)
        token_json = token_response.json()
        
        if 'access_token' not in token_json:
            flash('Failed to get access token from Google', 'error')
            return redirect(url_for('enhanced_auth.login'))
        
        # Get user info from Google
        user_response = requests.get(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f"Bearer {token_json['access_token']}"}
        )
        user_info = user_response.json()
        
        # Authenticate or create user
        user = enhanced_db.authenticate_google_user(
            google_id=user_info['id'],
            email=user_info['email'],
            full_name=user_info['name']
        )
        
        if user:
            login_user(user, remember=True)
            # Store success message in session for dashboard display
            session['login_success'] = f'Welcome back, {user.full_name}! Successfully signed in with Google.'
            return redirect(url_for('enhanced_auth.dashboard'))
        else:
            flash('Failed to authenticate with Google', 'error')
            
    except Exception as e:
        flash('Google authentication error occurred', 'error')
    
    return redirect(url_for('enhanced_auth.login'))

@enhanced_auth_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin():
        return render_template('enhanced_auth/admin_dashboard.html')
    elif current_user.is_doctor():
        return render_template('enhanced_auth/doctor_dashboard.html')
    elif current_user.is_patient():
        return render_template('enhanced_auth/patient_dashboard.html')
    else:
        # Default to patient dashboard for unknown roles
        return render_template('enhanced_auth/patient_dashboard.html')

@enhanced_auth_bp.route('/api/dashboard-stats')
@login_required
def dashboard_stats():
    """Get dashboard statistics for the logged-in doctor"""
    try:
        from patient_models import PatientDatabase
        from database import Database
        
        # Get doctor identifier
        doctor_id = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
        
        # Initialize databases
        patient_db = PatientDatabase()
        diagnosis_db = Database()
        
        # Get patient count for this doctor
        patients = patient_db.get_all_patients()
        my_patients = [p for p in patients if p.get('created_by') == doctor_id]
        
        # Get diagnosis count for this doctor
        diagnoses = patient_db.get_all_diagnoses()
        my_diagnoses = [d for d in diagnoses if d.get('created_by') == doctor_id]
        
        # Get today's date for appointments (placeholder - no appointment system yet)
        today = datetime.now().date()
        
        # Count code translations (search operations by this doctor)
        search_count = diagnosis_db.get_user_search_count(doctor_id)
        
        stats = {
            'my_patients': len(my_patients),
            'todays_appointments': 0,  # Placeholder - no appointment system
            'prescriptions': len(my_diagnoses),  # Using diagnoses as prescriptions
            'code_translations': search_count
        }
        
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({
            'my_patients': 0,
            'todays_appointments': 0,
            'prescriptions': 0,
            'code_translations': 0
        })

@enhanced_auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('oauth_state', None)
    session.pop('login_success', None)  # Clear any stored messages
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('enhanced_auth.login'))

# Role-based access decorators
def admin_required(f):
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Admin access required', 'error')
            return redirect(url_for('enhanced_auth.login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def doctor_required(f):
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not (current_user.is_doctor() or current_user.is_admin()):
            flash('Doctor access required', 'error')
            return redirect(url_for('enhanced_auth.login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@enhanced_auth_bp.route('/admin/users')
@admin_required
def admin_users():
    return jsonify({'message': 'Admin users page', 'user': current_user.full_name})

@enhanced_auth_bp.route('/doctor/patients')
@doctor_required
def doctor_patients():
    return jsonify({'message': 'Doctor patients page', 'user': current_user.full_name})

@enhanced_auth_bp.route('/check-username', methods=['POST'])
def check_username():
    data = request.get_json()
    username = data.get('username', '').strip()
    
    if not username or len(username) < 3:
        return jsonify({'available': False, 'message': 'Username too short'})
    
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return jsonify({'available': False, 'message': 'Invalid characters'})
    
    available = not enhanced_db.user_exists(username)
    return jsonify({'available': available})

@enhanced_auth_bp.route('/check-email', methods=['POST'])
def check_email():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    
    if not email or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        return jsonify({'available': False, 'message': 'Invalid email format'})
    
    available = not enhanced_db.email_exists(email)
    return jsonify({'available': available})