"""
Fraud Detection Hooks, Velocity Checks, Anomaly Scoring, Rate Limits, and Account Freeze Triggers.
"""

import time
from typing import Dict, List, Tuple
import threading

class FraudEngine:
    """Manages transaction velocity checks, anomaly scoring, rate limits, and freeze triggers."""

    def __init__(self, max_tx_per_minute: int = 10, anomaly_threshold: float = 85.0):
        self.max_tx_per_minute = max_tx_per_minute
        self.anomaly_threshold = anomaly_threshold
        # Account activity: account_id -> list of timestamps
        self._user_velocity: Dict[str, List[float]] = {}
        # Frozen accounts: account_id -> freeze reason string
        self._frozen_accounts: Dict[str, str] = {}
        self._lock = threading.Lock()

    def is_frozen(self, account_id: str) -> Tuple[bool, str]:
        with self._lock:
            if account_id in self._frozen_accounts:
                return True, self._frozen_accounts[account_id]
            return False, ""

    def freeze_account(self, account_id: str, reason: str):
        with self._lock:
            self._frozen_accounts[account_id] = reason

    def unfreeze_account(self, account_id: str):
        with self._lock:
            self._frozen_accounts.pop(account_id, None)

    def record_activity_and_check_velocity(self, account_id: str) -> bool:
        """
        Records action timestamp and checks per-minute rate limit / velocity.
        Returns True if within velocity limit, False if limit exceeded.
        """
        now = time.time()
        one_minute_ago = now - 60.0

        with self._lock:
            if account_id in self._frozen_accounts:
                return False

            timestamps = self._user_velocity.get(account_id, [])
            # Filter timestamps within last 60 seconds
            valid_timestamps = [t for t in timestamps if t > one_minute_ago]
            valid_timestamps.append(now)
            self._user_velocity[account_id] = valid_timestamps

            if len(valid_timestamps) > self.max_tx_per_minute:
                # Trigger automatic freeze on velocity spike
                self._frozen_accounts[account_id] = "Automatic freeze: Velocity limit exceeded"
                return False

            return True

    def calculate_anomaly_score(self, account_id: str, amount: float, ip_address: str, hour_of_day: int) -> dict:
        """
        Evaluates risk signals and generates a normalized risk/anomaly score (0 - 100).
        """
        score = 0.0
        reasons = []

        # Signal 1: High Transaction Amount
        if amount > 50000.0:
            score += 40.0
            reasons.append("High amount transaction exceeding $50,000 threshold")
        elif amount > 10000.0:
            score += 20.0
            reasons.append("Elevated transaction amount")

        # Signal 2: Unusual hours (e.g., 2 AM - 4 AM)
        if 2 <= hour_of_day <= 4:
            score += 15.0
            reasons.append("Transaction during off-peak hours")

        # Signal 3: Account velocity check
        with self._lock:
            velocity_count = len(self._user_velocity.get(account_id, []))
            if velocity_count > 5:
                score += 30.0
                reasons.append("High frequency account activity detected")

        frozen, freeze_reason = self.is_frozen(account_id)
        if frozen:
            score = 100.0
            reasons.append(f"Account is currently frozen: {freeze_reason}")

        recommendation = "ALLOW"
        if score >= self.anomaly_threshold:
            recommendation = "BLOCK_AND_FREEZE"
            self.freeze_account(account_id, f"High anomaly risk score ({score:.1f})")
        elif score >= 50.0:
            recommendation = "REQUIRE_MFA"

        return {
            'account_id': account_id,
            'score': min(score, 100.0),
            'threshold': self.anomaly_threshold,
            'recommendation': recommendation,
            'reasons': reasons
        }


fraud_engine = FraudEngine()
