import uuid
from peoples_coin.extensions import db
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

class MintIntent(db.Model):
    __tablename__ = 'mint_intents'
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goodwill_action_id = Column(PG_UUID(as_uuid=True), ForeignKey('goodwill_actions.id', ondelete='RESTRICT'), nullable=False, unique=True)
    idempotency_key = Column(String(100), nullable=False, unique=True)
    recipient_address = Column(String(128), nullable=False)
    amount = Column(String(80), nullable=False)
    state = Column(String(20), nullable=False, default='PENDING')
    tx_hash = Column(String(128), unique=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text)
    audit_trace_id = Column(String(255))
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

class MintOutbox(db.Model):
    __tablename__ = 'mint_outbox'
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mint_intent_id = Column(PG_UUID(as_uuid=True), ForeignKey('mint_intents.id', ondelete='CASCADE'), nullable=False, unique=True)
    topic = Column(String(100), nullable=False, default='mint.goodwill')
    payload = Column(JSONB, nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
