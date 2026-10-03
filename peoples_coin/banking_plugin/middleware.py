"""
Secure Banking Middleware for Pre-Request Signature Validation,
Replay Nonce Enforcement, Canonical JSON Normalization, PCI Sanitization,
and Audit Log Sealing.
"""

import os
import hmac
import hashlib
import json
import math
import time
from typing import Any, Optional
from flask import request, jsonify, g
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from .store import security_store, SecurityStoreUnavailable


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
        except (TypeError, ValueError):
            return False

        now = time.time()
        if not math.isfinite(ts_float) or abs(now - ts_float) > max_skew_seconds:
            return False

        expected_sig = cls.calculate_hmac(secret_key, timestamp, nonce, body)
        if not hmac.compare_digest(expected_sig, client_signature):
            return False

        # A unique key is the cross-worker compare-and-set. Expired rows are
        # removed in the same write transaction before reservation.
        try:
            with security_store.transaction(immediate=True) as conn:
                conn.execute(text("DELETE FROM banking_nonces WHERE expires_at <= :now"), {"now": now})
                conn.execute(text("INSERT INTO banking_nonces(nonce, expires_at, created_at) VALUES (:n,:e,:c)"),
                             {"n": nonce, "e": now + max_skew_seconds, "c": now})
            return True
        except IntegrityError:
            return False
        except SecurityStoreUnavailable:
            return False


def clean_expired_nonces(now: Optional[float] = None):
    """Remove expired nonces without racing verification requests."""
    now = time.time() if now is None else now
    with security_store.transaction(immediate=True) as conn:
        conn.execute(text("DELETE FROM banking_nonces WHERE expires_at <= :now"), {"now": now})


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
