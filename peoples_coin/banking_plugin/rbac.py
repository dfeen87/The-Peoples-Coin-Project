"""
Role-Based Access Control (RBAC) and Hardware-Bound MFA for Banking Security Plugin.
Supported Roles: customer, teller, auditor, admin.
Strict fail-closed enforcement on role mismatch or missing MFA hardware signatures.
"""

from functools import wraps
import time
import hmac
import hashlib
from typing import Dict, List, Optional
from flask import request, jsonify, g

ROLE_HIERARCHY = {
    'admin': {'admin', 'auditor', 'teller', 'customer'},
    'auditor': {'auditor', 'customer'},
    'teller': {'teller', 'customer'},
    'customer': {'customer'}
}

_EPHEMERAL_SESSIONS: Dict[str, dict] = {}


class RBACManager:
    """Manages role-based access control and hardware-bound ephemeral MFA session tokens."""

    @staticmethod
    def register_session(
        token: str,
        role: str,
        user_id: str,
        hardware_device_id: Optional[str] = None,
        ttl_seconds: int = 3600
    ) -> dict:
        if role not in ROLE_HIERARCHY:
            raise ValueError(f"Invalid role: {role}")

        expires_at = time.time() + ttl_seconds
        session = {
            'token': token,
            'role': role,
            'user_id': user_id,
            'hardware_device_id': hardware_device_id,
            'expires_at': expires_at,
            'permissions': sorted(list(ROLE_HIERARCHY[role]))
        }
        _EPHEMERAL_SESSIONS[token] = session
        return session

    @staticmethod
    def get_session(token: str) -> Optional[dict]:
        session = _EPHEMERAL_SESSIONS.get(token)
        if not session:
            return None
        if time.time() > session['expires_at']:
            del _EPHEMERAL_SESSIONS[token]
            return None
        return session

    @staticmethod
    def revoke_session(token: str):
        if token in _EPHEMERAL_SESSIONS:
            del _EPHEMERAL_SESSIONS[token]

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
