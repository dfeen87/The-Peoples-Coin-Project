"""
Dedicated Banking Endpoints & Blueprint definition.
Routes:
- /banking/verify-signature
- /banking/audit-proof
- /banking/fraud-score
- /banking/rbac/roles
All routes adopt strict fail-closed mode.
"""

from flask import Blueprint, request, jsonify, g, current_app
from .pci import pci_manager
from .audit import audit_log
from .fraud import fraud_engine
from .rbac import rbac_manager, require_role
from .tracing import regulated_tracer
from .middleware import RequestSigner

banking_plugin_blueprint = Blueprint('banking_plugin', __name__, url_prefix='/banking')


@banking_plugin_blueprint.route('/verify-signature', methods=['POST'])
def verify_signature():
    """Verify dual signature and HMAC payload with strict fail-closed rejection."""
    data = request.get_json(silent=True) or {}
    signature = request.headers.get('X-Banking-Signature') or data.get('signature')
    timestamp = request.headers.get('X-Banking-Timestamp') or data.get('timestamp')
    nonce = request.headers.get('X-Banking-Nonce') or data.get('nonce')
    payload = data.get('payload', {})

    secret_key = current_app.config.get('SECRET_KEY', 'default-secret-key')

    valid = RequestSigner.verify_request_signature(
        client_signature=signature,
        secret_key=secret_key,
        timestamp=str(timestamp) if timestamp else "",
        nonce=str(nonce) if nonce else "",
        body=payload
    )

    trace_id = getattr(g, 'banking_trace_id', None) or request.headers.get('X-FINRA-Trace-ID') or regulated_tracer.generate_trace_id()
    audit_log.append(
        event_type="SIGNATURE_VERIFICATION",
        actor=data.get('actor_id', 'anonymous'),
        context={'valid': valid, 'ip': request.remote_addr},
        trace_id=trace_id
    )

    if not valid:
        return jsonify({
            'valid': False,
            'code': 'INVALID_SIGNATURE',
            'error': 'Strict fail-closed: invalid signature, expired timestamp, or replayed nonce'
        }), 401

    return jsonify({
        'valid': True,
        'trace_id': trace_id,
        'status': 'SIGNATURE_VERIFIED'
    }), 200


@banking_plugin_blueprint.route('/audit-proof', methods=['GET'])
def audit_proof():
    """Retrieve Merkle root and tamper-evident snapshot with fail-closed integrity assertion."""
    snapshot = audit_log.get_snapshot()
    integrity_valid = audit_log.verify_integrity()

    if not integrity_valid:
        return jsonify({
            'integrity_verified': False,
            'code': 'MALFORMED_AUDIT_PROOF',
            'error': 'Strict fail-closed: audit log hash chain tamper or corruption detected'
        }), 422

    return jsonify({
        'integrity_verified': True,
        'snapshot': snapshot,
        'recent_entries_count': snapshot['total_records']
    }), 200


@banking_plugin_blueprint.route('/fraud-score', methods=['POST'])
def calculate_fraud_score():
    """Calculate anomaly score & velocity check with fail-closed rejection on threshold breach."""
    data = request.get_json(silent=True) or {}
    account_id = data.get('account_id')
    amount = float(data.get('amount', 0.0))
    ip_address = request.remote_addr or data.get('ip_address', '127.0.0.1')
    hour_of_day = int(data.get('hour_of_day', 12))

    if not account_id:
        return jsonify({
            'error': 'Strict fail-closed: account_id is required',
            'code': 'MISSING_ACCOUNT_ID'
        }), 400

    velocity_ok = fraud_engine.record_activity_and_check_velocity(account_id)
    assessment = fraud_engine.calculate_anomaly_score(
        account_id=account_id,
        amount=amount,
        ip_address=ip_address,
        hour_of_day=hour_of_day
    )

    trace_id = getattr(g, 'banking_trace_id', None) or request.headers.get('X-FINRA-Trace-ID') or regulated_tracer.generate_trace_id()
    audit_log.append(
        event_type="FRAUD_ASSESSMENT",
        actor=account_id,
        context=pci_manager.zero_log_dict(assessment),
        trace_id=trace_id
    )

    # Fail-closed check: reject if velocity exceeded or anomaly score threshold breached
    if not velocity_ok or assessment.get('recommendation') == 'BLOCK_AND_FREEZE':
        return jsonify({
            'velocity_ok': velocity_ok,
            'assessment': assessment,
            'trace_id': trace_id,
            'code': 'FRAUD_THRESHOLD_BREACH',
            'error': 'Strict fail-closed: fraud threshold breach or account freeze active'
        }), 403

    return jsonify({
        'velocity_ok': velocity_ok,
        'assessment': assessment,
        'trace_id': trace_id
    }), 200


@banking_plugin_blueprint.route('/rbac/roles', methods=['GET', 'POST'])
def manage_roles():
    """Endpoint to inspect or request ephemeral RBAC sessions."""
    if request.method == 'GET':
        return jsonify({
            'available_roles': ['customer', 'teller', 'auditor', 'admin'],
            'hierarchy': {
                'admin': ['admin', 'auditor', 'teller', 'customer'],
                'auditor': ['auditor', 'customer'],
                'teller': ['teller', 'customer'],
                'customer': ['customer']
            }
        }), 200

    data = request.get_json(silent=True) or {}
    token = data.get('token')
    role = data.get('role')
    user_id = data.get('user_id')
    hw_id = data.get('hardware_device_id')

    if not token or not role or not user_id:
        return jsonify({
            'error': 'Strict fail-closed: token, role, and user_id are required',
            'code': 'INVALID_RBAC_REQUEST'
        }), 400

    try:
        session = rbac_manager.register_session(token, role, user_id, hardware_device_id=hw_id)
        return jsonify({
            'status': 'SESSION_REGISTERED',
            'session': session
        }), 201
    except ValueError as e:
        return jsonify({
            'error': f'Strict fail-closed: {str(e)}',
            'code': 'RBAC_MISMATCH'
        }), 400
