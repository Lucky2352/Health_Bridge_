from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from db import singleton
from enhanced_auth import EnhancedAuthDB, UserRole
from diagnosis_models import DiagnosisDatabase
from patient_models import PatientDatabase
from database import Database
import os
import re
import logging
from datetime import datetime, timedelta
from functools import wraps
import requests as http_requests

# Configure logging
logger = logging.getLogger(__name__)

# Create Blueprint
enhanced_auth_bp = Blueprint('enhanced_auth', __name__, url_prefix='/enhanced')

@singleton
def get_enhanced_db():
    """Process-wide EnhancedAuthDB, built on first use."""
    return EnhancedAuthDB()

@singleton
def get_clinical_db():
    """Process-wide DiagnosisDatabase, built on first use."""
    return DiagnosisDatabase()

@singleton
def get_patient_db():
    """Process-wide PatientDatabase, built on first use."""
    return PatientDatabase()

@singleton
def get_search_db():
    """Process-wide Database (the search-operation log), built on first use."""
    return Database()

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_REDIRECT_URI = "http://localhost:8000/enhanced/google-callback"

def _google_client_id():
    return os.getenv("GOOGLE_CLIENT_ID", "")

def _google_client_secret():
    return os.getenv("GOOGLE_CLIENT_SECRET", "")

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
        
        user = get_enhanced_db().authenticate_user(username, password)
        
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
        
        if get_enhanced_db().email_exists(email):
            errors.append('Email address is already registered')
        
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters')
        elif not re.match(r'^[a-zA-Z0-9_]+$', username):
            errors.append('Username can only contain letters, numbers, and underscores')
        elif get_enhanced_db().user_exists(username):
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
            user_id = get_enhanced_db().create_user(username, email, full_name, password, role)
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
    client_id = _google_client_id()
    if not client_id:
        flash('Google login is not configured yet. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to your .env file.', 'error')
        return redirect(url_for('enhanced_auth.login'))

    import secrets
    state = secrets.token_urlsafe(16)
    session['oauth_state'] = state

    redirect_uri = GOOGLE_REDIRECT_URI
    auth_url = (
        f"{GOOGLE_AUTH_URL}"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=openid+email+profile"
        f"&response_type=code"
        f"&state={state}"
        f"&access_type=offline"
        f"&prompt=select_account"
    )
    return redirect(auth_url)


@enhanced_auth_bp.route('/google-callback')
def google_callback():
    # Validate state to prevent CSRF
    expected_state = session.pop('oauth_state', None)
    received_state = request.args.get('state')

    if not expected_state or not received_state or expected_state != received_state:
        logger.warning(f"OAuth state mismatch — expected: {expected_state}, got: {received_state}")
        # If session was lost but redirect succeeded, continue anyway (dev mode)
        if not expected_state:
            logger.warning("Session lost during OAuth redirect — proceeding without state check")
        else:
            flash('Authentication failed: session expired. Please try again.', 'error')
            return redirect(url_for('enhanced_auth.login'))

    error = request.args.get('error')
    if error:
        flash(f'Google login cancelled or failed: {error}', 'error')
        return redirect(url_for('enhanced_auth.login'))

    code = request.args.get('code')
    if not code:
        flash('No authorisation code received from Google.', 'error')
        return redirect(url_for('enhanced_auth.login'))

    # Exchange code for tokens
    try:
        token_resp = http_requests.post(GOOGLE_TOKEN_URL, data={
            'client_id': _google_client_id(),
            'client_secret': _google_client_secret(),
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': GOOGLE_REDIRECT_URI,
        }, timeout=10)
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception as e:
        logger.error(f"Google token exchange failed: {e}")
        flash('Failed to connect to Google. Please try again.', 'error')
        return redirect(url_for('enhanced_auth.login'))

    access_token = token_data.get('access_token')
    if not access_token:
        flash('Google did not return an access token.', 'error')
        return redirect(url_for('enhanced_auth.login'))

    # Fetch user info
    try:
        user_resp = http_requests.get(
            GOOGLE_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )
        user_resp.raise_for_status()
        user_info = user_resp.json()
    except Exception as e:
        logger.error(f"Google userinfo fetch failed: {e}")
        flash('Failed to retrieve your Google profile. Please try again.', 'error')
        return redirect(url_for('enhanced_auth.login'))

    google_id = user_info.get('id')
    email = user_info.get('email', '').lower()
    full_name = user_info.get('name', email.split('@')[0])

    if not google_id or not email:
        flash('Could not retrieve your Google account details.', 'error')
        return redirect(url_for('enhanced_auth.login'))

    # Try to authenticate / create user (no role yet for new users)
    user, is_new = get_enhanced_db().authenticate_google_user(google_id, email, full_name)

    if user is None and is_new:
        # New user — store Google info in session and ask for role
        session['pending_google'] = {
            'google_id': google_id,
            'email': email,
            'full_name': full_name
        }
        return redirect(url_for('enhanced_auth.google_role_select'))

    if user:
        login_user(user, remember=True)
        session['login_success'] = f'Welcome{" back" if not is_new else ""}, {user.full_name}!'
        return redirect(url_for('enhanced_auth.dashboard'))

    flash('Google authentication failed. Please try again.', 'error')
    return redirect(url_for('enhanced_auth.login'))


@enhanced_auth_bp.route('/google-role-select', methods=['GET', 'POST'])
def google_role_select():
    """Ask new Google users to pick Doctor or Patient before creating their account."""
    pending = session.get('pending_google')
    if not pending:
        return redirect(url_for('enhanced_auth.login'))

    if request.method == 'POST':
        role = request.form.get('role', '').strip()
        if role not in ('doctor', 'patient'):
            flash('Please select a valid account type.', 'error')
            return render_template('enhanced_auth/google_role_select.html',
                                   full_name=pending['full_name'], email=pending['email'])

        user, _ = get_enhanced_db().authenticate_google_user(
            pending['google_id'], pending['email'], pending['full_name'], role=role
        )
        session.pop('pending_google', None)

        if user:
            login_user(user, remember=True)
            session['login_success'] = f'Welcome to HealthBridge, {user.full_name}!'
            return redirect(url_for('enhanced_auth.dashboard'))

        flash('Account creation failed. Please try again.', 'error')
        return redirect(url_for('enhanced_auth.login'))

    return render_template('enhanced_auth/google_role_select.html',
                           full_name=pending['full_name'], email=pending['email'])

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

def _on_date(value, target):
    """Whether a timestamp falls on *target*.

    PostgreSQL hands back a datetime and SQLite hands back a string, so this goes
    through str() rather than calling .date() on whatever arrived.
    """
    if not value:
        return False
    try:
        return datetime.fromisoformat(str(value).replace('Z', '')).date() == target
    except (TypeError, ValueError):
        return False

@enhanced_auth_bp.route('/api/dashboard-stats')
@login_required
def dashboard_stats():
    """Get dashboard statistics for the logged-in doctor"""
    try:
        # Two different identifiers are in play here. patients.created_by stores the
        # clinician's username, while diagnoses/prescriptions/treatments key off the
        # immutable doctor_id. Keep them apart rather than reusing one name.
        created_by = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
        doctor_code = getattr(current_user, 'doctor_id', None)
        
        # Only two numbers are needed here, so they are counted by the database
        # rather than by pulling every row in both tables across the wire and
        # filtering in Python. Same predicate, same counts, no transfer.
        my_patients = get_patient_db().count_patients(created_by)
        my_diagnoses = get_patient_db().count_diagnoses(created_by)
        
        # Count code translations (search operations by this doctor)
        search_count = get_search_db().get_user_search_count(created_by)
        
        # Prescriptions and treatment plans belong to a doctor by doctor_id, not by
        # the username the patient register uses. A doctor without one (an admin, or
        # an unassigned account) has authored neither.
        my_treatments = get_clinical_db().get_doctor_treatments(doctor_code) if doctor_code else []

        # Appointment requests are addressed to a doctor by doctor_id, same as
        # treatments. Only 'scheduled' rows count as a day's diary: a request the
        # doctor has not answered yet is not booked, so it is counted separately as
        # something waiting for them.
        my_appointments = get_clinical_db().get_doctor_appointments(doctor_code) if doctor_code else []
        today = datetime.now().date()
        todays_appointments = sum(
            1 for a in my_appointments
            if a.get('status') == 'scheduled' and _on_date(a.get('appointment_date'), today)
        )

        stats = {
            'my_patients': my_patients,
            'todays_appointments': todays_appointments,
            'pending_appointment_requests': sum(
                1 for a in my_appointments if a.get('status') == 'pending'
            ),
            'diagnoses': my_diagnoses,
            'prescriptions': 0,  # No route writes the prescriptions table yet
            'treatments': len(my_treatments),
            'active_treatments': sum(1 for t in my_treatments if t.get('status') == 'active'),
            'code_translations': search_count
        }
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error('Dashboard stats failed: %s', e)
        return jsonify({
            'my_patients': 0,
            'todays_appointments': 0,
            'pending_appointment_requests': 0,
            'diagnoses': 0,
            'prescriptions': 0,
            'treatments': 0,
            'active_treatments': 0,
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


def is_clinician():
    """True when the signed-in user is a doctor or an admin.

    Single source of truth for "may this account handle patient records", shared
    by the /patients blueprint guard and the app-level routes below so the rule
    cannot drift apart between call sites.
    """
    return bool(
        current_user.is_authenticated
        and (current_user.is_doctor() or current_user.is_admin())
    )


def clinician_required(f):
    """Restrict a view to doctors and admins."""

    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not is_clinician():
            flash('Clinician access required', 'error')
            return redirect(url_for('enhanced_auth.dashboard'))
        return f(*args, **kwargs)

    return decorated_function


def may_read_patient_record(patient_id):
    """May the signed-in user read the record belonging to *patient_id*?

    A patient may only read their own record, identified by the patient_id on
    their own session - never one supplied in the URL. Doctors and admins may
    read any record.
    """
    if not current_user.is_authenticated:
        return False
    if is_clinician():
        return True
    own = getattr(current_user, 'patient_id', None)
    return bool(current_user.is_patient() and own and own == patient_id)

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
    
    available = not get_enhanced_db().user_exists(username)
    return jsonify({'available': available})

@enhanced_auth_bp.route('/check-email', methods=['POST'])
def check_email():
    data = request.get_json()
    email = data.get('email', '').strip().lower()
    
    if not email or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        return jsonify({'available': False, 'message': 'Invalid email format'})
    
    available = not get_enhanced_db().email_exists(email)
    return jsonify({'available': available})