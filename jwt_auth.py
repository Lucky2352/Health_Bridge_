import jwt
import uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app

class JWTAuth:
    SECRET_KEY = 'your-jwt-secret-key-change-in-production'
    
    @staticmethod
    def generate_token(username, expires_hours=24):
        """Generate JWT token"""
        payload = {
            'username': username,
            'exp': datetime.utcnow() + timedelta(hours=expires_hours),
            'iat': datetime.utcnow(),
            'jti': str(uuid.uuid4())
        }
        
        return jwt.encode(payload, JWTAuth.SECRET_KEY, algorithm='HS256')
    
    @staticmethod
    def verify_token(token):
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, JWTAuth.SECRET_KEY, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

def jwt_required(f):
    """JWT authentication decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        
        # Check Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'error': 'JWT token is missing'}), 401
        
        payload = JWTAuth.verify_token(token)
        if not payload:
            return jsonify({'error': 'JWT token is invalid or expired'}), 401
        
        # Add user info to request context
        request.jwt_user = payload['username']
        
        return f(*args, **kwargs)
    
    return decorated_function