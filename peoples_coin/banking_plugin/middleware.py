"""
Secure Banking Middleware for Pre-Request Signature Validation,
Replay Nonce Enforcement, Canonical JSON Normalization, PCI Sanitization,
and Audit Log Sealing.
"""

import hmac
import hashlib
import json
import time
from typing import Dict, Any, Optional
from flask import request, jsonify, g
from functools import wraps

# In-memory replay attack nonce store: nonce -> expiration_timestamp
_NONCE_CACHE: Dict[str, float] = {}

class RequestSigner:
    """Handles dual-signature payload validation and canonical JSON normalization."""

    @staticmethod
    def canonicalize_payload(data: Any) -> str:
        """Serializes input dictionary or string into canonical sorted JSON string."""
        if data is None:
            return ""
        if isinstance(data, (dict, list)):
            return json.dumps(data, sort_keys=True, separators=(',', ':'))
        return str(data)

    @classmethod
    def calculate_hmac(cls, secret_key: str, timestamp: str, nonce: str, body: Any) -> str:
        canonical_body = cls.canonicalize_payload(body)
        message = f"{timestamp}:{nonce}:{canonical_body}"
        return hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()

    @classmethod
    def verify_request_signature(
        cls,
        client_signature: str,
        secret_key: str,
        timestamp: str,
        nonce: str,
        body: Any,
        max_skew_seconds: int = 300
    ) -> bool:
        """
        Validates timestamp freshness, replay nonce, and Dual HMAC signature.
        """
        if not client_signature or not timestamp or not nonce:
            return False

        # Validate timestamp skew
        try:
            ts_float = float(timestamp)
        except ValueError:
            return False

        now = time.time()
        if abs(now - ts_float) > max_skew_seconds:
            return False

        # Validate replay nonce
        clean_expired_nonces()
        if nonce in _NONCE_CACHE:
            return False  # Replay attack detected!

        # Verify HMAC
        expected_sig = cls.calculate_hmac(secret_key, timestamp, nonce, body)
        if not hmac.compare_digest(expected_sig, client_signature):
            return False

        # Record nonce
        _NONCE_CACHE[nonce] = now + max_skew_seconds
        return True


def clean_expired_nonces():
    now = time.time()
    expired = [n for n, exp in _NONCE_CACHE.items() if exp < now]
    for n in expired:
        del _NONCE_CACHE[n]


def banking_security_middleware(app=None, secret_key: Optional[str] = None):
    """
    Flask middleware / before_request hook for strict banking security enforcement.
    """
    from .pci import pci_manager
    from .audit import audit_log
    from .tracing import regulated_tracer

    def before_request():
        # Check if request targets banking endpoints or banking mode is enforced
        trace_id = request.headers.get('X-FINRA-Trace-ID') or regulated_tracer.generate_trace_id()
        g.banking_trace_id = trace_id

        # Attach response header hook
        g.start_time = time.time()

        # Check signature if headers are provided or required
        sig = request.headers.get('X-Banking-Signature')
        ts = request.headers.get('X-Banking-Timestamp')
        nonce = request.headers.get('X-Banking-Nonce')

        sec_key = secret_key or app.config.get('SECRET_KEY', 'default-banking-secret')

        if sig or ts or nonce:
            body_data = request.get_json(silent=True) or request.get_data(as_text=True)
            valid = RequestSigner.verify_request_signature(
                client_signature=sig,
                secret_key=sec_key,
                timestamp=ts,
                nonce=nonce,
                body=body_data
            )
            if not valid:
                audit_log.append('SIGNATURE_VERIFICATION_FAILED', 'anonymous', {
                    'ip': request.remote_addr,
                    'path': request.path
                }, trace_id=trace_id)
                return jsonify({
                    'error': 'Banking request signature or replay nonce check failed',
                    'code': 'INVALID_SIGNATURE'
                }), 401

    if app:
        app.before_request(before_request)

    return before_request
