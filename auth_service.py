import sqlite3
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash

class AuthService:
    def __init__(self, db_file='diagnosis.db'):
        self.db_file = db_file
        self.init_users_table()
        self.create_default_user()
    
    def init_users_table(self):
        conn = sqlite3.connect(self.db_file)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
    
    def create_default_user(self):
        # Create default doctor account
        conn = sqlite3.connect(self.db_file)
        cursor = conn.execute('SELECT COUNT(*) FROM users WHERE username = ?', ('doctor',))
        if cursor.fetchone()[0] == 0:
            password_hash = generate_password_hash('password123')
            conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', 
                        ('doctor', password_hash))
            conn.commit()
        conn.close()
    
    def validate_user(self, username, password):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.execute('SELECT password_hash FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        conn.close()
        
        if row and check_password_hash(row[0], password):
            return True
        return False
    
    def get_user(self, username):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        return dict(user) if user else None
    
    def create_user(self, username, password):
        """Create new user account"""
        try:
            password_hash = generate_password_hash(password)
            conn = sqlite3.connect(self.db_file)
            conn.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', 
                        (username, password_hash))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception:
            return False