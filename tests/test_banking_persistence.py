from concurrent.futures import ThreadPoolExecutor
import time

from sqlalchemy import text

from peoples_coin.banking_plugin.store import SecurityStore
from peoples_coin.banking_plugin.rbac import RBACManager
from peoples_coin.banking_plugin.fraud import FraudEngine
from peoples_coin.banking_plugin.audit import TamperEvidentAuditLog
from peoples_coin.banking_plugin import middleware


def store(tmp_path):
    return SecurityStore(f"sqlite:///{tmp_path / 'shared.db'}")


def test_session_survives_manager_restart_and_revocation(tmp_path):
    shared = store(tmp_path)
    first, restarted = RBACManager(shared), RBACManager(shared)
    first.register_session("secret", "auditor", "user", ttl_seconds=60)
    assert restarted.get_session("secret")["user_id"] == "user"
    restarted.revoke_session("secret")
    assert first.get_session("secret") is None
    first.register_session("short", "customer", "user", ttl_seconds=1)
    with shared.transaction(immediate=True) as conn:
        conn.execute(text("UPDATE banking_sessions SET expires_at=:past WHERE token_hash=:h"),
                     {"past": time.time()-1, "h": __import__('hashlib').sha256(b'short').hexdigest()})
    assert restarted.get_session("short") is None


def test_atomic_velocity_across_independent_engines(tmp_path):
    shared = store(tmp_path)
    engines = [FraudEngine(max_tx_per_minute=2, store=shared) for _ in range(3)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda engine: engine.record_activity_and_check_velocity("account"), engines))
    assert results.count(True) == 2
    assert engines[0].velocity_count("account") == 2
    assert engines[1].is_frozen("account")[0]


def test_concurrent_nonce_has_one_winner(tmp_path, monkeypatch):
    shared = store(tmp_path)
    monkeypatch.setattr(middleware, "security_store", shared)
    timestamp = str(time.time())
    signature = middleware.RequestSigner.calculate_hmac("key", timestamp, "nonce", {})
    def verify(_):
        return middleware.RequestSigner.verify_request_signature(signature, "key", timestamp, "nonce", {})
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(verify, range(12)))
    assert results.count(True) == 1


def test_audit_persists_is_owned_and_concurrent_appends_order(tmp_path):
    shared = store(tmp_path)
    log = TamperEvidentAuditLog(shared)
    context = {"nested": {"ok": True}}
    log.append("FIRST", "actor", context)
    context["nested"]["ok"] = False
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: TamperEvidentAuditLog(shared).append("EVENT", str(i), {"i": i}), range(20)))
    restarted = TamperEvidentAuditLog(SecurityStore(shared.url))
    entries = restarted.get_entries(100)
    assert entries[0]["context"]["nested"]["ok"] is True
    assert [entry["index"] for entry in entries] == list(range(21))
    assert restarted.verify_integrity()
