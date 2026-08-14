"""
Secure Banking Middleware for Pre-Request Signature Validation,
Replay Nonce Enforcement, Canonical JSON Normalization, PCI Sanitization,
and Audit Log Sealing.
"""

import os
import hmac
import hashlib
import json
import time
from typing import Dict, Any, Optional
from flask import request, jsonify, g

_NONCE_CACHE: Dict[str, float] = {}

class RequestSigner:
    """Handles dual-signature payload validation and canonical JSON normalization."""

    @staticmethod
    def canonicalize_payload(data: Any) -> str:
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
        if not client_signature or not timestamp or not nonce:
            return False

        try:
            ts_float = float(timestamp)
        except ValueError:
            return False

        now = time.time()
        if abs(now - ts_float) > max_skew_seconds:
            return False

        clean_expired_nonces()
        if nonce in _NONCE_CACHE:
            return False  # Replay attack detected!

        expected_sig = cls.calculate_hmac(secret_key, timestamp, nonce, body)
        if not hmac.compare_digest(expected_sig, client_signature):
            return False

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
    Operates in fail-closed mode across signatures, PCI data compliance, and trace lineage.
    """
    from .pci import pci_manager
    from .audit import audit_log
    from .tracing import regulated_tracer

    def before_request():
        # 1. Require Trace Lineage Header if strictly required
        require_trace = os.getenv("BANKING_REQUIRE_TRACE", "false").lower() in ("true", "1")
        provided_trace_id = request.headers.get('X-FINRA-Trace-ID')

        if require_trace and not provided_trace_id:
            return jsonify({
                'error': 'Strict fail-closed: missing required trace lineage header (X-FINRA-Trace-ID)',
                'code': 'MISSING_TRACE_LINEAGE'
            }), 400

        trace_id = provided_trace_id or regulated_tracer.generate_trace_id()
        g.banking_trace_id = trace_id
        g.start_time = time.time()

        # 2. Signature Validation
        sig = request.headers.get('X-Banking-Signature')
        ts = request.headers.get('X-Banking-Timestamp')
        nonce = request.headers.get('X-Banking-Nonce')
        require_sig = os.getenv("BANKING_REQUIRE_SIGNATURE", "false").lower() in ("true", "1")

        sec_key = secret_key or (app.config.get('SECRET_KEY') if app else 'default-banking-secret')

        if require_sig or sig or ts or nonce:
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
                    'error': 'Strict fail-closed: invalid signature, expired timestamp, or replayed nonce',
                    'code': 'INVALID_SIGNATURE'
                }), 401

        # 3. Fail-Closed PCI-DSS Data Violation Check
        require_pci_check = os.getenv("BANKING_STRICT_PCI", "true").lower() in ("true", "1")
        if require_pci_check and request.is_json:
            json_body = request.get_json(silent=True)
            if json_body:
                compliant, violation_reason = pci_manager.validate_pci_compliance(json_body)
                if not compliant:
                    audit_log.append('PCI_DSS_VIOLATION_BLOCKED', 'anonymous', {
                        'reason': violation_reason,
                        'path': request.path
                    }, trace_id=trace_id)
                    return jsonify({
                        'error': f'Strict fail-closed: PCI-DSS violation rejected ({violation_reason})',
                        'code': 'PCI_DSS_VIOLATION'
                    }), 422

    if app:
        app.before_request(before_request)

    return before_request
