"""shared security state and mint outbox

Revision ID: 6f1d2a3b4c5d
Revises: eaa8dc007009
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='6f1d2a3b4c5d'; down_revision='eaa8dc007009'; branch_labels=None; depends_on=None

def upgrade():
    op.create_table('banking_nonces',sa.Column('nonce',sa.String(255),primary_key=True),sa.Column('expires_at',sa.Float(),nullable=False),sa.Column('created_at',sa.Float(),nullable=False))
    op.create_table('banking_sessions',sa.Column('token_hash',sa.String(64),primary_key=True),sa.Column('role',sa.String(32),nullable=False),sa.Column('user_id',sa.String(255),nullable=False),sa.Column('hardware_device_id',sa.String(255)),sa.Column('expires_at',sa.Float(),nullable=False),sa.Column('revoked_at',sa.Float()),sa.Column('created_at',sa.Float(),nullable=False))
    op.create_table('banking_fraud_accounts',sa.Column('account_id',sa.String(255),primary_key=True),sa.Column('frozen_reason',sa.Text()),sa.Column('updated_at',sa.Float(),nullable=False))
    op.create_table('banking_fraud_events',sa.Column('id',sa.String(36),primary_key=True),sa.Column('account_id',sa.String(255),nullable=False),sa.Column('occurred_at',sa.Float(),nullable=False)); op.create_index('ix_banking_fraud_window','banking_fraud_events',['account_id','occurred_at'])
    op.create_table('banking_audit_entries',sa.Column('sequence',sa.BigInteger(),sa.Identity(),primary_key=True),sa.Column('timestamp',sa.Float(),nullable=False),sa.Column('event_type',sa.String(255),nullable=False),sa.Column('actor',sa.String(255),nullable=False),sa.Column('context_json',sa.Text(),nullable=False),sa.Column('trace_id',sa.String(255)),sa.Column('previous_hash',sa.String(64),nullable=False),sa.Column('entry_hash',sa.String(64),nullable=False,unique=True))
    op.create_table('mint_intents',sa.Column('id',postgresql.UUID(as_uuid=True),primary_key=True),sa.Column('goodwill_action_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('goodwill_actions.id',ondelete='RESTRICT'),nullable=False,unique=True),sa.Column('idempotency_key',sa.String(100),nullable=False,unique=True),sa.Column('recipient_address',sa.String(128),nullable=False),sa.Column('amount',sa.String(80),nullable=False),sa.Column('state',sa.String(20),nullable=False),sa.Column('tx_hash',sa.String(128),unique=True),sa.Column('attempts',sa.Integer(),nullable=False,server_default='0'),sa.Column('last_error',sa.Text()),sa.Column('audit_trace_id',sa.String(255)),sa.Column('next_attempt_at',sa.DateTime(timezone=True)),sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_table('mint_outbox',sa.Column('id',postgresql.UUID(as_uuid=True),primary_key=True),sa.Column('mint_intent_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('mint_intents.id',ondelete='CASCADE'),nullable=False,unique=True),sa.Column('topic',sa.String(100),nullable=False),sa.Column('payload',postgresql.JSONB(),nullable=False),sa.Column('attempts',sa.Integer(),nullable=False,server_default='0'),sa.Column('available_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column('published_at',sa.DateTime(timezone=True)),sa.Column('last_error',sa.Text()),sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))

def downgrade():
    for table in ('mint_outbox','mint_intents','banking_audit_entries','banking_fraud_events','banking_fraud_accounts','banking_sessions','banking_nonces'): op.drop_table(table)
