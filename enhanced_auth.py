import sqlite3
import os
import logging
from datetime import datetime, timedelta
from flask_login import UserMixin
from enum import Enum
from werkzeug.security import generate_password_hash, check_password_hash

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UserRole(Enum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    PATIENT = "patient"

class EnhancedUser(UserMixin):
    def __init__(self, id, username, email, full_name, role, created_at, last_login=None, patient_id=None, doctor_id=None):
        self.id = id
        self.username = username
        self.email = email
        self.full_name = full_name
        self.role = role
        self.patient_id = patient_id
        self.doctor_id = doctor_id
        self.created_at = created_at
        self.last_login = last_login
    
    def get_id(self):
        return str(self.id)
    
    def has_role(self, role):
        return self.role == role.value if isinstance(role, UserRole) else self.role == role
    
    def is_admin(self):
        return self.role == UserRole.ADMIN.value
    
    def is_doctor(self):
        return self.role == UserRole.DOCTOR.value
    
    def is_patient(self):
        return self.role == UserRole.PATIENT.value

class EnhancedAuthDB:
    def __init__(self, db_file='enhanced_auth.db'):
        # Convert to absolute path to ensure single database file
        if not os.path.isabs(db_file):
            self.db_file = os.path.abspath(db_file)
        else:
            self.db_file = db_file
        logger.info(f"Using database file: {self.db_file}")
        self.init_database()
        self.create_default_users()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_file)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS enhanced_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                full_name TEXT NOT NULL,
                password_hash TEXT,
                role TEXT DEFAULT 'patient',
                patient_id TEXT UNIQUE,
                doctor_id TEXT UNIQUE,
                google_id TEXT UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login DATETIME,
                is_active BOOLEAN DEFAULT 1,
                remember_token TEXT
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                session_token TEXT UNIQUE,
                expires_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES enhanced_users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def create_default_users(self):
        """Create default users for each role"""
        defaults = [
            ('admin', 'admin@emr.com', 'System Administrator', 'admin123', UserRole.ADMIN.value),
            ('doctor', 'doctor@emr.com', 'Dr. John Smith', 'doctor123', UserRole.DOCTOR.value),
            ('patient', 'patient@emr.com', 'Jane Doe', 'patient123', UserRole.PATIENT.value)
        ]
        
        for username, email, full_name, password, role in defaults:
            if not self.user_exists(username):
                self.create_user(username, email, full_name, password, role)
    
    def generate_patient_id(self):
        """Generate unique patient ID in format P0001, P0002, etc."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.execute('SELECT COUNT(*) FROM enhanced_users WHERE role = "patient"')
        patient_count = cursor.fetchone()[0]
        conn.close()
        return f"P{patient_count + 1:04d}"
    
    def generate_doctor_id(self):
        """Generate unique doctor ID in format D0001, D0002, etc."""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.execute('SELECT COUNT(*) FROM enhanced_users WHERE role = "doctor"')
        doctor_count = cursor.fetchone()[0]
        conn.close()
        return f"D{doctor_count + 1:04d}"
    
    def create_user(self, username, email, full_name, password, role=UserRole.PATIENT.value, google_id=None):
        try:
            # Normalize inputs
            username = username.strip()
            email = email.strip().lower()
            full_name = full_name.strip()
            
            # Generate password hash using werkzeug
            password_hash = None
            if password:
                password_hash = generate_password_hash(password)
            
            # Generate patient_id for patients and doctor_id for doctors
            patient_id = None
            doctor_id = None
            if role == 'patient':
                patient_id = self.generate_patient_id()
            elif role == 'doctor':
                doctor_id = self.generate_doctor_id()
            
            logger.info(f"Creating user: {username} ({email}) with patient_id: {patient_id}, doctor_id: {doctor_id}")
            
            conn = sqlite3.connect(self.db_file)
            cursor = conn.execute('''
                INSERT INTO enhanced_users (username, email, full_name, password_hash, role, patient_id, doctor_id, google_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (username, email, full_name, password_hash, role, patient_id, doctor_id, google_id))
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            
            logger.info(f"User created successfully: {username} (ID: {user_id}, Patient ID: {patient_id}, Doctor ID: {doctor_id})")
            return user_id
        except sqlite3.IntegrityError as e:
            logger.error(f"User creation failed for {username}: {e}")
            if 'username' in str(e):
                raise ValueError('Username already exists')
            elif 'email' in str(e):
                raise ValueError('Email already exists')
            else:
                raise ValueError('User creation failed')
        except Exception as e:
            logger.error(f"Unexpected error creating user {username}: {e}")
            raise ValueError('User creation failed')
    
    def authenticate_user(self, username_or_email, password):
        # Normalize input
        username_or_email = username_or_email.strip().lower() if '@' in username_or_email else username_or_email.strip()
        
        logger.info(f"Login attempt for: {username_or_email}")
        
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        
        if '@' in username_or_email:
            cursor = conn.execute('''
                SELECT * FROM enhanced_users 
                WHERE email = ? AND is_active = 1
            ''', (username_or_email,))
        else:
            cursor = conn.execute('''
                SELECT * FROM enhanced_users 
                WHERE username = ? AND is_active = 1
            ''', (username_or_email,))
        
        user_row = cursor.fetchone()
        
        if user_row and user_row['password_hash']:
            password_hash = user_row['password_hash']
            password_valid = False
            
            # Handle both bcrypt (bytes) and werkzeug (string) formats
            if isinstance(password_hash, bytes):
                # Legacy bcrypt format - import bcrypt for backward compatibility
                try:
                    import bcrypt
                    password_valid = bcrypt.checkpw(password.encode('utf-8'), password_hash)
                    logger.info(f"Used bcrypt verification for legacy user: {username_or_email}")
                except ImportError:
                    logger.error("bcrypt not available for legacy password verification")
            else:
                # New werkzeug format
                password_valid = check_password_hash(password_hash, password)
                logger.info(f"Used werkzeug verification for user: {username_or_email}")
            
            if password_valid:
                logger.info(f"Login successful for: {username_or_email}")
                self.update_last_login(user_row['id'])
                conn.close()
                return self._create_user_object(user_row)
        
        conn.close()
        logger.warning(f"Login failed for: {username_or_email}")
        return None
    
    def authenticate_google_user(self, google_id, email, full_name):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        
        # Check if user exists with Google ID
        cursor = conn.execute('''
            SELECT * FROM enhanced_users 
            WHERE google_id = ? AND is_active = 1
        ''', (google_id,))
        user_row = cursor.fetchone()
        
        if not user_row:
            # Check if user exists with email
            cursor = conn.execute('''
                SELECT * FROM enhanced_users 
                WHERE email = ? AND is_active = 1
            ''', (email,))
            user_row = cursor.fetchone()
            
            if user_row:
                # Link Google account to existing user
                conn.execute('''
                    UPDATE enhanced_users 
                    SET google_id = ? 
                    WHERE id = ?
                ''', (google_id, user_row['id']))
                conn.commit()
            else:
                # Create new user with doctor role (same as signup)
                username = email.split('@')[0]
                counter = 1
                original_username = username
                
                while self.user_exists(username):
                    username = f"{original_username}{counter}"
                    counter += 1
                
                conn.execute('''
                    INSERT INTO enhanced_users (username, email, full_name, role, google_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (username, email, full_name, UserRole.DOCTOR.value, google_id))
                conn.commit()
                
                cursor = conn.execute('''
                    SELECT * FROM enhanced_users 
                    WHERE google_id = ?
                ''', (google_id,))
                user_row = cursor.fetchone()
        
        conn.close()
        
        if user_row:
            self.update_last_login(user_row['id'])
            return self._create_user_object(user_row)
        
        return None
    
    def get_user_by_id(self, user_id):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('''
            SELECT * FROM enhanced_users 
            WHERE id = ? AND is_active = 1
        ''', (user_id,))
        user_row = cursor.fetchone()
        conn.close()
        
        if user_row:
            return self._create_user_object(user_row)
        return None
    
    def _create_user_object(self, user_row):
        return EnhancedUser(
            id=user_row['id'],
            username=user_row['username'],
            email=user_row['email'],
            full_name=user_row['full_name'],
            role=user_row['role'],
            patient_id=user_row['patient_id'] if 'patient_id' in user_row.keys() else None,
            doctor_id=user_row['doctor_id'] if 'doctor_id' in user_row.keys() else None,
            created_at=user_row['created_at'],
            last_login=user_row['last_login']
        )
    
    def update_last_login(self, user_id):
        conn = sqlite3.connect(self.db_file)
        conn.execute('''
            UPDATE enhanced_users 
            SET last_login = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (user_id,))
        conn.commit()
        conn.close()
    
    def user_exists(self, username):
        username = username.strip()
        conn = sqlite3.connect(self.db_file)
        cursor = conn.execute('SELECT COUNT(*) FROM enhanced_users WHERE username = ?', (username,))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    
    def email_exists(self, email):
        email = email.strip().lower()
        conn = sqlite3.connect(self.db_file)
        cursor = conn.execute('SELECT COUNT(*) FROM enhanced_users WHERE email = ?', (email,))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    
    def get_user_by_email(self, email):
        email = email.strip().lower()
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('SELECT * FROM enhanced_users WHERE email = ? AND is_active = 1', (email,))
        user_row = cursor.fetchone()
        conn.close()
        
        if user_row:
            return self._create_user_object(user_row)
        return None
    
    def get_user_by_username(self, username):
        username = username.strip()
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('SELECT * FROM enhanced_users WHERE username = ? AND is_active = 1', (username,))
        user_row = cursor.fetchone()
        conn.close()
        
        if user_row:
            return self._create_user_object(user_row)
        return None
    
    def get_user_by_patient_id(self, patient_id):
        """Get user by patient_id"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('SELECT * FROM enhanced_users WHERE patient_id = ? AND is_active = 1', (patient_id,))
        user_row = cursor.fetchone()
        conn.close()
        
        if user_row:
            return self._create_user_object(user_row)
        return None
    
    def get_user_by_doctor_id(self, doctor_id):
        """Get user by doctor_id"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('SELECT * FROM enhanced_users WHERE doctor_id = ? AND is_active = 1', (doctor_id,))
        user_row = cursor.fetchone()
        conn.close()
        
        if user_row:
            return self._create_user_object(user_row)
        return None