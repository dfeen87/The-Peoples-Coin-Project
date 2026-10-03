import os
import json
import time
import pytest
from flask import Flask, jsonify

from peoples_coin.banking_plugin import (
    pci_manager,
    rbac_manager,
    require_role,
    audit_log,
    fraud_engine,
    regulated_tracer,
    RequestSigner,
    banking_plugin_blueprint,
    banking_security_middleware
)


@pytest.fixture
def banking_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-secret-key'
    app.register_blueprint(banking_plugin_blueprint)
    banking_security_middleware(app, secret_key='test-secret-key')

    @app.route('/protected-admin', methods=['GET'])
    @require_role('admin', require_mfa_hardware=True)
    def protected_admin_endpoint():
        return jsonify({'status': 'granted'}), 200

    return app


@pytest.fixture
def client(banking_app):
    return banking_app.test_client()


def test_pci_pan_masking():
    pan = "4111111111111111"
    masked = pci_manager.mask_pan(pan)
    assert masked == "************1111"

    ssn = "123-45-6789"
    masked_ssn = pci_manager.mask_ssn(ssn)
    assert masked_ssn == "***-**-6789"


def test_pci_dict_sanitization():
    sensitive_data = {
        'user_id': 'u123',
        'card_number': '4111111111111111',
        'ssn': '123-45-6789',
        'password': 'supersecretpass'
    }
    sanitized = pci_manager.sanitize_dict(sensitive_data)
    assert sanitized['user_id'] == 'u123'
    assert sanitized['card_number'] == '************1111'
    assert sanitized['ssn'] == '***-**-6789'
    assert sanitized['password'] == '[REDACTED]'


def test_pci_zero_log_dict():
    sensitive_data = {
        'user_id': 'u123',
        'card_number': '4111111111111111',
        'ssn': '123-45-6789',
        'public_info': 'hello'
    }
    zero_logged = pci_manager.zero_log_dict(sensitive_data)
    assert 'card_number' not in zero_logged
    assert 'ssn' not in zero_logged
    assert zero_logged['public_info'] == 'hello'


def test_rbac_session_management():
    session = rbac_manager.register_session('token-123', 'teller', 'user-456')
    assert session['role'] == 'teller'
    assert 'teller' in session['permissions']
    assert 'customer' in session['permissions']
    assert 'admin' not in session['permissions']

    fetched = rbac_manager.get_session('token-123')
    assert fetched is not None
    assert fetched['user_id'] == 'user-456'


def test_audit_merkle_tree():
    audit_log.append('TEST_EVENT_1', 'user1', {'key': 'val1'})
    audit_log.append('TEST_EVENT_2', 'user2', {'key': 'val2'})

    root = audit_log.get_merkle_root()
    assert isinstance(root, str)
    assert len(root) == 64  # SHA256 length

    assert audit_log.verify_integrity() is True


def test_fraud_engine_velocity_and_scoring():
    account_id = "acc_test_999"
    fraud_engine.unfreeze_account(account_id)

    assessment = fraud_engine.calculate_anomaly_score(
        account_id=account_id,
        amount=100000.0,
        ip_address="192.168.1.1",
        hour_of_day=3
    )
    assert assessment['score'] >= 50.0

    for _ in range(15):
        fraud_engine.record_activity_and_check_velocity(account_id)

    frozen, reason = fraud_engine.is_frozen(account_id)
    assert frozen is True


def test_regulated_tracer():
    trace_id = regulated_tracer.generate_trace_id()
    assert trace_id.startswith("FINRA-TRACE-")

    lineage = regulated_tracer.create_lineage_record(
        trace_id=trace_id,
        action="TRANSFER",
        actor_id="actor_123",
        resource_id="res_456"
    )
    assert lineage['trace_id'] == trace_id
    assert lineage['retention_policy']['retention_years'] == 7


def test_endpoint_audit_proof(client):
    res = client.get('/banking/audit-proof')
    assert res.status_code == 200
    data = res.get_json()
    assert data['integrity_verified'] is True
    assert 'merkle_root' in data['snapshot']


def test_endpoint_fraud_score(client):
    res = client.post('/banking/fraud-score', json={
        'account_id': 'test_acc_100',
        'amount': 500.0,
        'hour_of_day': 14
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['velocity_ok'] is True
    assert 'score' in data['assessment']


def test_endpoint_verify_signature(client):
    secret = 'test-secret-key'
    timestamp = str(time.time())
    nonce = 'nonce-unique-001'
    payload = {'action': 'TRANSFER', 'amount': 100}

    sig = RequestSigner.calculate_hmac(secret, timestamp, nonce, payload)

    res = client.post('/banking/verify-signature', json={
        'signature': sig,
        'timestamp': timestamp,
        'nonce': nonce,
        'payload': payload
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['valid'] is True


def test_endpoint_rbac_roles(client):
    res = client.get('/banking/rbac/roles')
    assert res.status_code == 200
    data = res.get_json()
    assert 'admin' in data['available_roles']

    rbac_manager.register_session('provisioner-token', 'admin', 'provisioner')
    reg_res = client.post('/banking/rbac/roles', headers={
        'Authorization': 'Bearer provisioner-token'
    }, json={
        'token': 'bearer-token-abc',
        'role': 'admin',
        'user_id': 'admin_001'
    })
    assert reg_res.status_code == 201


def test_rbac_session_issuance_requires_admin(client):
    """An anonymous or lower-privileged caller cannot mint an admin session."""
    payload = {'token': 'forged-admin', 'role': 'admin', 'user_id': 'attacker'}
    assert client.post('/banking/rbac/roles', json=payload).status_code == 401

    rbac_manager.register_session('customer-token', 'customer', 'customer')
    response = client.post(
        '/banking/rbac/roles',
        headers={'Authorization': 'Bearer customer-token'},
        json=payload,
    )
    assert response.status_code == 403
    assert rbac_manager.get_session('forged-admin') is None


@pytest.mark.parametrize('amount', ['NaN', 'Infinity', '-1', True])
def test_fraud_score_rejects_invalid_amount_without_recording_activity(client, amount):
    account_id = f'invalid-amount-{amount}'
    response = client.post('/banking/fraud-score', json={
        'account_id': account_id,
        'amount': amount,
    })
    assert response.status_code == 400
    assert response.get_json()['code'] == 'INVALID_FRAUD_REQUEST'
    assert fraud_engine.velocity_count(account_id) == 0


@pytest.mark.parametrize('hour', [-1, 24, 1.5, True, 'not-an-hour'])
def test_fraud_score_rejects_invalid_hour_without_recording_activity(client, hour):
    account_id = f'invalid-hour-{hour}'
    response = client.post('/banking/fraud-score', json={
        'account_id': account_id,
        'amount': 1,
        'hour_of_day': hour,
    })
    assert response.status_code == 400
    assert response.get_json()['code'] == 'INVALID_FRAUD_REQUEST'
    assert fraud_engine.velocity_count(account_id) == 0


def test_signature_rejects_non_finite_timestamp(client):
    timestamp = 'nan'
    nonce = 'non-finite-timestamp'
    payload = {'action': 'TRANSFER'}
    signature = RequestSigner.calculate_hmac(
        'test-secret-key', timestamp, nonce, payload
    )
    response = client.post('/banking/verify-signature', json={
        'signature': signature,
        'timestamp': timestamp,
        'nonce': nonce,
        'payload': payload,
    })
    assert response.status_code == 401


def test_audit_log_defensively_copies_context_and_entries(tmp_path):
    from peoples_coin.banking_plugin.audit import TamperEvidentAuditLog
    from peoples_coin.banking_plugin.store import SecurityStore

    log = TamperEvidentAuditLog(
        SecurityStore(f"sqlite:///{tmp_path / 'defensive-copy-audit.db'}")
    )
    context = {'nested': {'approved': True}}
    returned = log.append('DECISION', 'actor', context)
    context['nested']['approved'] = False
    returned['context']['nested']['approved'] = False

    entries = log.get_entries()
    entries[0]['context']['nested']['approved'] = False

    assert log.verify_integrity() is True
    assert log.get_entries()[0]['context']['nested']['approved'] is True


def test_audit_integrity_detects_hash_index_corruption(tmp_path):
    from peoples_coin.banking_plugin.audit import TamperEvidentAuditLog
    from peoples_coin.banking_plugin.store import SecurityStore
    from sqlalchemy import text

    log = TamperEvidentAuditLog(SecurityStore(f"sqlite:///{tmp_path / 'audit.db'}"))
    entry = log.append('DECISION', 'actor', {})
    with log.store.transaction(immediate=True) as conn:
        conn.execute(text("UPDATE banking_audit_entries SET entry_hash=:bad WHERE entry_hash=:old"),
                     {'bad': '0' * 64, 'old': entry['hash']})
    assert log.verify_integrity() is False


# --- Fail-Closed Rejection Tests ---

def test_fail_closed_invalid_signature(client):
    res = client.post('/banking/verify-signature', json={
        'signature': 'invalid-signature-hash',
        'timestamp': str(time.time()),
        'nonce': 'nonce-123',
        'payload': {'action': 'PAYMENT'}
    })
    assert res.status_code == 401
    data = res.get_json()
    assert data['code'] == 'INVALID_SIGNATURE'


def test_fail_closed_pci_violation(client):
    res = client.post('/banking/fraud-score', json={
        'account_id': 'acc_123',
        'card_number': '4111111111111111',  # Raw unmasked PAN
        'amount': 100.0
    })
    assert res.status_code == 422
    data = res.get_json()
    assert data['code'] == 'PCI_DSS_VIOLATION'


def test_fail_closed_fraud_threshold(client):
    fraud_acc = "fraud_blocked_acc"
    fraud_engine.freeze_account(fraud_acc, "Manual security freeze")

    res = client.post('/banking/fraud-score', json={
        'account_id': fraud_acc,
        'amount': 500.0
    })
    assert res.status_code == 403
    data = res.get_json()
    assert data['code'] == 'FRAUD_THRESHOLD_BREACH'


def test_fail_closed_missing_trace_lineage(banking_app):
    os.environ['BANKING_REQUIRE_TRACE'] = 'true'
    try:
        test_client = banking_app.test_client()
        res = test_client.get('/banking/rbac/roles')
        assert res.status_code == 400
        data = res.get_json()
        assert data['code'] == 'MISSING_TRACE_LINEAGE'
    finally:
        os.environ['BANKING_REQUIRE_TRACE'] = 'false'


def test_fail_closed_rbac_mismatch_and_mfa(client):
    # 1. No token -> 401
    res1 = client.get('/protected-admin')
    assert res1.status_code == 401
    assert res1.get_json()['code'] == 'UNAUTHORIZED'

    # 2. Teller token attempting admin route -> 403 RBAC_MISMATCH
    rbac_manager.register_session('teller-tok', 'teller', 'user_teller')
    res2 = client.get('/protected-admin', headers={'Authorization': 'Bearer teller-tok'})
    assert res2.status_code == 403
    assert res2.get_json()['code'] == 'RBAC_MISMATCH'

    # 3. Admin token missing hardware MFA signature -> 403 MISSING_MFA_TOKEN
    rbac_manager.register_session('admin-tok', 'admin', 'user_admin', hardware_device_id='hw_dev_99')
    res3 = client.get('/protected-admin', headers={'Authorization': 'Bearer admin-tok'})
    assert res3.status_code == 403
    assert res3.get_json()['code'] == 'MISSING_MFA_TOKEN'


def test_fail_closed_malformed_audit_proof(client):
    from sqlalchemy import text
    entry = audit_log.append("PRE_TAMPER_EVENT", "actor1", {})
    with audit_log.store.transaction(immediate=True) as conn:
        conn.execute(text("UPDATE banking_audit_entries SET previous_hash=:bad WHERE entry_hash=:h"),
                     {'bad': 'corrupted_hash_value_12345', 'h': entry['hash']})

    res = client.get('/banking/audit-proof')
    assert res.status_code == 422
    data = res.get_json()
    assert data['code'] == 'MALFORMED_AUDIT_PROOF'
