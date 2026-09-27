# src/peoples_coin/utils/auth.py

import http
import logging
from datetime import datetime, timezone
from functools import wraps
from flask import request, jsonify, g
from firebase_admin import auth as firebase_auth
from peoples_coin.extensions import db
from peoples_coin.models import ApiKey

logger = logging.getLogger(__name__)
KEY_ERROR = "error"


# ------------------------------------------------------------------------------
# Firebase Auth Support
# ------------------------------------------------------------------------------

class FirebaseUser:
    """Lightweight object to hold Firebase-authenticated user info."""
    def __init__(self, uid, email=None, username=None):
        self.firebase_uid = uid
        self.email = email
        self.username = username


def require_firebase_token(f):
    """Decorator to protect routes with a Firebase ID token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        scheme, separator, id_token = (auth_header or "").partition(" ")
        if scheme.lower() != "bearer" or not separator or not id_token.strip():
            return jsonify({KEY_ERROR: "Missing or invalid Authorization header"}), http.HTTPStatus.UNAUTHORIZED

        id_token = id_token.strip()

        try:
            decoded_token = firebase_auth.verify_id_token(id_token)
            uid = decoded_token.get("uid")
            email = decoded_token.get("email")
            display_name = decoded_token.get("name")

            if not uid:
                return jsonify({KEY_ERROR: "Invalid token: no UID"}), http.HTTPStatus.UNAUTHORIZED

            # Attach FirebaseUser object directly to g.user
            g.user = FirebaseUser(
                uid=uid,
                email=email,
                username=display_name or (email.split("@")[0] if email else None)
            )

        except Exception as e:
            logger.error(f"Firebase token verification failed: {e}")
            return jsonify({KEY_ERROR: "Invalid, expired, or revoked token"}), http.HTTPStatus.UNAUTHORIZED

        return f(*args, **kwargs)
    return decorated


# ------------------------------------------------------------------------------
# API Key Auth Support
# ------------------------------------------------------------------------------

def require_api_key(f):
    """Decorator to require a valid API key via 'X-API-Key' header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return jsonify({KEY_ERROR: "API key missing"}), http.HTTPStatus.UNAUTHORIZED

        try:
            # Look up the API key in the database
            key_obj = db.session.query(ApiKey).filter_by(key=api_key).first()

            if not key_obj:
                return jsonify({KEY_ERROR: "Invalid API key"}), http.HTTPStatus.FORBIDDEN

            # Check expiration
            if key_obj.expires_at:
                expires_at = key_obj.expires_at
                now = datetime.now(timezone.utc if expires_at.tzinfo else None)
                if expires_at < now:
                    return jsonify({KEY_ERROR: "API key expired"}), http.HTTPStatus.FORBIDDEN

            # Attach the API key's user to g.api_user for downstream use
            g.api_user = key_obj.user

        except Exception as e:
            logger.error(f"API key validation failed: {e}")
            return jsonify({KEY_ERROR: "Internal authentication error"}), http.HTTPStatus.INTERNAL_SERVER_ERROR

        return f(*args, **kwargs)
    return decorated
