import os
import json
import time
import pytest
from flask import Flask

from peoples_coin.banking_plugin import (
    pci_manager,
    rbac_manager,
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

    # Reset account state
    fraud_engine.unfreeze_account(account_id)

    assessment = fraud_engine.calculate_anomaly_score(
        account_id=account_id,
        amount=100000.0,  # High amount (>50k adds 40 pts)
        ip_address="192.168.1.1",
        hour_of_day=3      # Off-peak hours adds 15 pts
    )
    assert assessment['score'] >= 50.0

    # Test velocity limit
    for _ in range(15):
        fraud_engine.record_activity_and_check_velocity(account_id)

    frozen, reason = fraud_engine.is_frozen(account_id)
    assert frozen is True
    assert "Velocity" in reason or "anomaly" in reason


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

    reg_res = client.post('/banking/rbac/roles', json={
        'token': 'bearer-token-abc',
        'role': 'admin',
        'user_id': 'admin_001'
    })
    assert reg_res.status_code == 201
