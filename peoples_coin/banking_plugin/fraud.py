"""Database-backed atomic fraud velocity and freeze controls."""
import math
import time
import uuid
from numbers import Real
from typing import Tuple
from sqlalchemy import text
from .store import security_store


class FraudEngine:
    def __init__(self, max_tx_per_minute: int = 10, anomaly_threshold: float = 85.0, store=None):
        self.max_tx_per_minute = max_tx_per_minute
        self.anomaly_threshold = anomaly_threshold
        self.store = store or security_store

    @staticmethod
    def _validate_account(account_id):
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("account_id must be a non-empty string")

    def is_frozen(self, account_id: str) -> Tuple[bool, str]:
        self._validate_account(account_id)
        with self.store.transaction() as conn:
            reason = conn.execute(text("SELECT frozen_reason FROM banking_fraud_accounts WHERE account_id=:a"), {"a": account_id}).scalar()
        return (reason is not None, reason or "")

    def freeze_account(self, account_id: str, reason: str):
        self._validate_account(account_id)
        now = time.time()
        with self.store.transaction(immediate=True) as conn:
            conn.execute(text("INSERT INTO banking_fraud_accounts(account_id,frozen_reason,updated_at) VALUES (:a,:r,:n) ON CONFLICT(account_id) DO UPDATE SET frozen_reason=:r,updated_at=:n"), {"a": account_id, "r": reason, "n": now})

    def unfreeze_account(self, account_id: str):
        self._validate_account(account_id)
        now = time.time()
        with self.store.transaction(immediate=True) as conn:
            conn.execute(text("INSERT INTO banking_fraud_accounts(account_id,frozen_reason,updated_at) VALUES (:a,NULL,:n) ON CONFLICT(account_id) DO UPDATE SET frozen_reason=NULL,updated_at=:n"), {"a": account_id, "n": now})

    def record_activity_and_check_velocity(self, account_id: str) -> bool:
        self._validate_account(account_id)
        now = time.time()
        with self.store.transaction(immediate=True) as conn:
            conn.execute(text("INSERT INTO banking_fraud_accounts(account_id,frozen_reason,updated_at) VALUES (:a,NULL,:n) ON CONFLICT(account_id) DO NOTHING"), {"a": account_id, "n": now})
            lock_clause = " FOR UPDATE" if conn.dialect.name == "postgresql" else ""
            row = conn.execute(text("SELECT frozen_reason FROM banking_fraud_accounts WHERE account_id=:a" + lock_clause), {"a": account_id}).first()
            if row[0] is not None:
                return False
            conn.execute(text("DELETE FROM banking_fraud_events WHERE occurred_at <= :cutoff"), {"cutoff": now - 60})
            count = conn.execute(text("SELECT COUNT(*) FROM banking_fraud_events WHERE account_id=:a AND occurred_at>:cutoff"), {"a": account_id, "cutoff": now - 60}).scalar_one()
            if count >= self.max_tx_per_minute:
                conn.execute(text("UPDATE banking_fraud_accounts SET frozen_reason=:r,updated_at=:n WHERE account_id=:a"), {"r": "Automatic freeze: Velocity limit exceeded", "n": now, "a": account_id})
                return False
            conn.execute(text("INSERT INTO banking_fraud_events(id,account_id,occurred_at) VALUES (:i,:a,:n)"), {"i": str(uuid.uuid4()), "a": account_id, "n": now})
            return True

    def velocity_count(self, account_id: str) -> int:
        self._validate_account(account_id)
        with self.store.transaction() as conn:
            return conn.execute(text("SELECT COUNT(*) FROM banking_fraud_events WHERE account_id=:a AND occurred_at>:c"), {"a": account_id, "c": time.time()-60}).scalar_one()

    def calculate_anomaly_score(self, account_id: str, amount: float, ip_address: str, hour_of_day: int) -> dict:
        self._validate_account(account_id)
        if isinstance(amount, bool) or not isinstance(amount, Real) or not math.isfinite(float(amount)) or amount < 0:
            raise ValueError("amount must be a finite, non-negative number")
        if isinstance(hour_of_day, bool) or not isinstance(hour_of_day, int) or not 0 <= hour_of_day <= 23:
            raise ValueError("hour_of_day must be an integer from 0 through 23")
        score, reasons = 0.0, []
        if amount > 50000: score, reasons = score + 40, reasons + ["High amount transaction exceeding $50,000 threshold"]
        elif amount > 10000: score, reasons = score + 20, reasons + ["Elevated transaction amount"]
        if 2 <= hour_of_day <= 4: score, reasons = score + 15, reasons + ["Transaction during off-peak hours"]
        if self.velocity_count(account_id) > 5: score, reasons = score + 30, reasons + ["High frequency account activity detected"]
        frozen, reason = self.is_frozen(account_id)
        if frozen: score, reasons = 100, reasons + [f"Account is currently frozen: {reason}"]
        recommendation = "BLOCK_AND_FREEZE" if score >= self.anomaly_threshold else "REQUIRE_MFA" if score >= 50 else "ALLOW"
        if recommendation == "BLOCK_AND_FREEZE": self.freeze_account(account_id, f"High anomaly risk score ({score:.1f})")
        return {'account_id': account_id, 'score': min(score, 100.0), 'threshold': self.anomaly_threshold, 'recommendation': recommendation, 'reasons': reasons}

fraud_engine = FraudEngine()
