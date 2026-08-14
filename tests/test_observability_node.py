"""
Tests for the Global Observability Node.

These tests verify that all endpoints work correctly and that
non-GET requests are properly rejected.
"""
import pytest
import json
from datetime import datetime, timezone
from observability_node.app import create_observability_app


@pytest.fixture
def app():
    """Create a test Flask application."""
    # Use SQLite for testing
    test_app = create_observability_app(db_uri='sqlite:///:memory:')
    test_app.config['TESTING'] = True
    
    with test_app.app_context():
        from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
        SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"
        import peoples_coin.models
        from peoples_coin.extensions import db as main_db
        from observability_node.app import db as obs_db
        main_db.metadata.create_all(bind=obs_db.engine)
    
    yield test_app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


def test_health_endpoint(client):
    """Test the /health endpoint."""
    response = client.get('/health')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert data['status'] == 'ok'
    assert data['service'] == 'Global Observability Node'
    assert 'version' in data
    assert 'uptime_seconds' in data
    assert 'timestamp' in data


def test_system_state_endpoint(client):
    """Test the /api/system_state endpoint."""
    response = client.get('/api/system_state')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert 'system_metrics' in data
    assert 'database_activity' in data
    assert 'kubernetes_enabled' in data
    assert 'timestamp' in data
    
    # Check system metrics structure
    metrics = data['system_metrics']
    assert 'cpu_percent' in metrics
    assert 'memory' in metrics
    assert 'disk' in metrics


def test_controller_decisions_endpoint(client):
    """Test the /api/controller_decisions endpoint."""
    response = client.get('/api/controller_decisions')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert 'count' in data
    assert 'limit' in data
    assert 'decisions' in data
    assert 'timestamp' in data
    assert data['count'] >= 0


def test_controller_decisions_with_limit(client):
    """Test the /api/controller_decisions endpoint with limit parameter."""
    response = client.get('/api/controller_decisions?limit=5')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert data['limit'] == 5


def test_governance_state_endpoint(client):
    """Test the /api/governance_state endpoint."""
    response = client.get('/api/governance_state')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert 'proposal_summary' in data
    assert 'vote_summary' in data
    assert 'council_summary' in data
    assert 'recent_proposals' in data
    assert 'timestamp' in data


def test_audit_summary_endpoint(client):
    """Test the /api/audit_summary endpoint."""
    response = client.get('/api/audit_summary')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert 'count' in data
    assert 'limit' in data
    assert 'audit_entries' in data
    assert 'timestamp' in data


def test_audit_summary_with_limit(client):
    """Test the /api/audit_summary endpoint with limit parameter."""
    response = client.get('/api/audit_summary?limit=20')
    assert response.status_code == 200
    
    data = json.loads(response.data)
    assert data['limit'] == 20


def test_post_request_rejected(client):
    """Test that POST requests are rejected with 405."""
    response = client.post('/health')
    assert response.status_code == 405
    
    data = json.loads(response.data)
    assert 'error' in data
    assert data['error'] == 'Method Not Allowed'


def test_put_request_rejected(client):
    """Test that PUT requests are rejected with 405."""
    response = client.put('/api/system_state')
    assert response.status_code == 405


def test_delete_request_rejected(client):
    """Test that DELETE requests are rejected with 405."""
    response = client.delete('/api/controller_decisions')
    assert response.status_code == 405


def test_patch_request_rejected(client):
    """Test that PATCH requests are rejected with 405."""
    response = client.patch('/api/governance_state')
    assert response.status_code == 405
