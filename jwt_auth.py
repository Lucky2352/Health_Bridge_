import os
import uuid
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify

class JWTAuth:
    """HS256 token helpers for the API routes.

    The signing secret is read from the JWT_SECRET_KEY environment variable
    every time a token is signed or verified. It is deliberately never
    hardcoded: the previous placeholder string was committed to source, so it
    was public to anyone with repo access.
    """

    @staticmethod
    def _secret_key():
        key = (os.getenv('JWT_SECRET_KEY') or '').strip()
        if not key:
            raise RuntimeError(
                'JWT_SECRET_KEY environment variable is not set. Generate a '
                'strong random value (python -c "import secrets; '
                'print(secrets.token_hex(32))") and add it to .env.'
            )
        return key

    @staticmethod
    def generate_token(username, expires_hours=24):
        """Generate JWT token"""
        import jwt
        payload = {
            'username': username,
            'exp': datetime.utcnow() + timedelta(hours=expires_hours),
            'iat': datetime.utcnow(),
            'jti': str(uuid.uuid4())
        }

        return jwt.encode(payload, JWTAuth._secret_key(), algorithm='HS256')

    @staticmethod
    def verify_token(token):
        """Verify JWT token"""
        # Resolved outside the try: a missing JWT_SECRET_KEY is a configuration
        # error, and swallowing it would report "invalid token" instead.
        secret = JWTAuth._secret_key()
        try:
            import jwt
            payload = jwt.decode(token, secret, algorithms=['HS256'])
            return payload
        except Exception:
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