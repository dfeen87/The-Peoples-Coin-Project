"""Durable, fail-closed storage used by banking security boundaries.

Production must point ``BANKING_STATE_DATABASE_URL`` at the same PostgreSQL
database used by every web worker.  The SQLite default is deliberately only a
single-host development default; unlike the old dictionaries it is durable and
coordinates independent local processes.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine


class SecurityStoreUnavailable(RuntimeError):
    pass


def _default_url() -> str:
    path = Path(os.getenv("BANKING_SQLITE_PATH", "instance/banking-security.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path.absolute()}"


class SecurityStore:
    def __init__(self, url: str | None = None):
        self.url = url or os.getenv("BANKING_STATE_DATABASE_URL") or os.getenv("DATABASE_URL") or _default_url()
        self.engine: Engine = create_engine(self.url, pool_pre_ping=True)
        if self.engine.dialect.name == "sqlite":
            event.listen(self.engine, "connect", lambda c, _: c.execute("PRAGMA busy_timeout=30000"))
        self._ensure_schema()

    def _ensure_schema(self):
        # Bootstrap is for development/tests. Production uses the Alembic
        # migration and can disable this with BANKING_AUTO_CREATE=false.
        if os.getenv("BANKING_AUTO_CREATE", "true").lower() not in {"1", "true", "yes"}:
            return
        statements = [
            "CREATE TABLE IF NOT EXISTS banking_nonces (nonce VARCHAR(255) PRIMARY KEY, expires_at FLOAT NOT NULL, created_at FLOAT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS banking_sessions (token_hash VARCHAR(64) PRIMARY KEY, role VARCHAR(32) NOT NULL, user_id VARCHAR(255) NOT NULL, hardware_device_id VARCHAR(255), expires_at FLOAT NOT NULL, revoked_at FLOAT, created_at FLOAT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS banking_fraud_accounts (account_id VARCHAR(255) PRIMARY KEY, frozen_reason TEXT, updated_at FLOAT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS banking_fraud_events (id VARCHAR(36) PRIMARY KEY, account_id VARCHAR(255) NOT NULL, occurred_at FLOAT NOT NULL)",
            "CREATE INDEX IF NOT EXISTS ix_banking_fraud_window ON banking_fraud_events(account_id, occurred_at)",
            "CREATE TABLE IF NOT EXISTS banking_audit_entries (sequence INTEGER PRIMARY KEY AUTOINCREMENT, timestamp FLOAT NOT NULL, event_type VARCHAR(255) NOT NULL, actor VARCHAR(255) NOT NULL, context_json TEXT NOT NULL, trace_id VARCHAR(255), previous_hash VARCHAR(64) NOT NULL, entry_hash VARCHAR(64) NOT NULL UNIQUE)",
        ]
        try:
            with self.engine.begin() as conn:
                for statement in statements:
                    # PostgreSQL identity syntax is handled by migration.
                    if self.engine.dialect.name != "sqlite" and "AUTOINCREMENT" in statement:
                        statement = statement.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
                    conn.exec_driver_sql(statement)
        except Exception as exc:
            raise SecurityStoreUnavailable("banking shared store initialization failed") from exc

    @contextmanager
    def transaction(self, immediate: bool = False):
        try:
            with self.engine.connect() as conn:
                if immediate and self.engine.dialect.name == "sqlite":
                    conn.exec_driver_sql("BEGIN IMMEDIATE")
                else:
                    conn.begin()
                try:
                    yield conn
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        except SecurityStoreUnavailable:
            raise
        except Exception as exc:
            raise SecurityStoreUnavailable("banking shared store operation failed") from exc


security_store = SecurityStore()
