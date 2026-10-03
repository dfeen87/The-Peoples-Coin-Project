"""
Role-Based Access Control (RBAC) and Hardware-Bound MFA for Banking Security Plugin.
Supported Roles: customer, teller, auditor, admin.
Strict fail-closed enforcement on role mismatch or missing MFA hardware signatures.
"""

from functools import wraps
import time
import hmac
import hashlib
from typing import Optional
from flask import request, jsonify, g
from sqlalchemy import text
from .store import security_store

ROLE_HIERARCHY = {
    'admin': {'admin', 'auditor', 'teller', 'customer'},
    'auditor': {'auditor', 'customer'},
    'teller': {'teller', 'customer'},
    'customer': {'customer'}
}

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class RBACManager:
    """Manages role-based access control and hardware-bound ephemeral MFA session tokens."""

    def __init__(self, store=None):
        self.store = store or security_store

    def register_session(
        self,
        token: str,
        role: str,
        user_id: str,
        hardware_device_id: Optional[str] = None,
        ttl_seconds: int = 3600
    ) -> dict:
        if not isinstance(token, str) or not token.strip():
            raise ValueError("Session token must be a non-empty string")
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("User ID must be a non-empty string")
        if role not in ROLE_HIERARCHY:
            raise ValueError(f"Invalid role: {role}")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise ValueError("Session TTL must be a positive integer")

        expires_at = time.time() + ttl_seconds
        session = {
            'token': token,
            'role': role,
            'user_id': user_id,
            'hardware_device_id': hardware_device_id,
            'expires_at': expires_at,
            'permissions': sorted(list(ROLE_HIERARCHY[role]))
        }
        now = time.time()
        with self.store.transaction(immediate=True) as conn:
            conn.execute(text("DELETE FROM banking_sessions WHERE token_hash=:h"), {"h": _token_hash(token)})
            conn.execute(text("INSERT INTO banking_sessions(token_hash,role,user_id,hardware_device_id,expires_at,revoked_at,created_at) VALUES (:h,:r,:u,:d,:e,NULL,:c)"),
                         {"h": _token_hash(token), "r": role, "u": user_id, "d": hardware_device_id, "e": expires_at, "c": now})
        return session.copy()

    def get_session(self, token: str) -> Optional[dict]:
        with self.store.transaction() as conn:
            row = conn.execute(text("SELECT role,user_id,hardware_device_id,expires_at,revoked_at FROM banking_sessions WHERE token_hash=:h"), {"h": _token_hash(token)}).mappings().first()
        if not row or row['revoked_at'] is not None or time.time() >= row['expires_at']:
            return None
        return {'token': token, 'role': row['role'], 'user_id': row['user_id'],
                'hardware_device_id': row['hardware_device_id'], 'expires_at': row['expires_at'],
                'permissions': sorted(ROLE_HIERARCHY[row['role']])}

    def revoke_session(self, token: str):
        with self.store.transaction(immediate=True) as conn:
            conn.execute(text("UPDATE banking_sessions SET revoked_at=:now WHERE token_hash=:h AND revoked_at IS NULL"),
                         {"now": time.time(), "h": _token_hash(token)})

    @staticmethod
    def verify_hardware_binding(session: dict, hardware_signature: Optional[str], payload: str) -> bool:
        hw_id = session.get('hardware_device_id')
        if not hw_id:
            return True

        if not hardware_signature:
            return False

        expected_sig = hmac.new(hw_id.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, hardware_signature)


rbac_manager = RBACManager()


def require_role(required_role: str, require_mfa_hardware: bool = False):
    """Decorator to enforce strict fail-closed RBAC and MFA hardware token checks."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            auth_header = request.headers.get('Authorization', '')
            token = auth_header.replace('Bearer ', '').strip() if auth_header.startswith('Bearer ') else ''

            if not token:
                return jsonify({
                    'error': 'Strict fail-closed: missing authentication token',
                    'code': 'UNAUTHORIZED'
                }), 401

            session = rbac_manager.get_session(token)
            if not session:
                return jsonify({
                    'error': 'Strict fail-closed: invalid or expired session token',
                    'code': 'UNAUTHORIZED'
                }), 401

            user_permissions = session.get('permissions', [])
            if required_role not in user_permissions:
                return jsonify({
                    'error': f'Strict fail-closed: role mismatch ({required_role} required)',
                    'code': 'RBAC_MISMATCH'
                }), 403

            if require_mfa_hardware:
                hw_sig = request.headers.get('X-Hardware-MFA-Signature')
                payload = request.get_data(as_text=True) or request.path
                if not hw_sig or not rbac_manager.verify_hardware_binding(session, hw_sig, payload):
                    return jsonify({
                        'error': 'Strict fail-closed: missing or invalid hardware-bound MFA token signature',
                        'code': 'MISSING_MFA_TOKEN'
                    }), 403

            g.banking_user = session
            return f(*args, **kwargs)
        return decorated
    return decorator
