"""Durable mint intent, transactional outbox, and conservative recovery worker."""
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from sqlalchemy.exc import IntegrityError
from peoples_coin.models import GoodwillAction, UserAccount, UserWallet, MintIntent, MintOutbox
from peoples_coin.banking_plugin.audit import audit_log

class MintingError(RuntimeError): pass
class AmbiguousSubmission(MintingError): pass

class MintingService:
    MAX_ATTEMPTS = 5
    def __init__(self, db, adapter=None): self.db, self.adapter = db, adapter
    @staticmethod
    def key(action_id): return f"goodwill:{action_id}"
    def create_intent(self, action_id, trace_id=None):
        """Atomically records eligibility and an outbox row; never publishes here."""
        session=self.db.session
        action=session.query(GoodwillAction).with_for_update().filter_by(id=action_id).one_or_none()
        if not action: raise MintingError("goodwill action not found")
        existing=session.query(MintIntent).filter_by(goodwill_action_id=action.id).one_or_none()
        if existing: return existing
        if action.status != 'VERIFIED': raise MintingError("only VERIFIED actions are mint eligible")
        wallet=session.query(UserWallet).filter_by(user_id=action.performer_user_id,is_primary=True).one_or_none()
        if not wallet: raise MintingError("eligible action has no primary wallet")
        try: amount=Decimal(action.loves_value)
        except InvalidOperation as exc: raise MintingError("invalid mint amount") from exc
        if amount <= 0: raise MintingError("mint amount must be positive")
        intent=MintIntent(goodwill_action_id=action.id,idempotency_key=self.key(action.id),recipient_address=wallet.public_address,amount=str(amount),state='PENDING',audit_trace_id=trace_id)
        session.add(intent); session.flush()
        session.add(MintOutbox(mint_intent_id=intent.id,payload={'mint_intent_id':str(intent.id),'idempotency_key':intent.idempotency_key}))
        audit_log.append('MINT_INTENT_CREATED',str(action.performer_user_id),{'intent_id':str(intent.id),'action_id':str(action.id)},trace_id)
        return intent
    def dispatch_batch(self, publisher, limit=100):
        """Publish committed rows. Marking after publish permits redelivery by design."""
        rows=(self.db.session.query(MintOutbox).filter(MintOutbox.published_at.is_(None),MintOutbox.available_at <= datetime.now(timezone.utc)).with_for_update(skip_locked=True).limit(limit).all())
        sent=0
        for row in rows:
            try:
                publisher.publish(row.topic,row.payload,message_id=str(row.id)); row.published_at=datetime.now(timezone.utc); sent+=1
            except Exception as exc:
                row.attempts += 1; row.last_error=str(exc)[:2000]; row.available_at=datetime.now(timezone.utc)+timedelta(seconds=min(300,2**min(row.attempts,8)))
        self.db.session.commit(); return sent
    def execute(self, intent_id):
        """Submit once, or reconcile an existing/ambiguous submission by stable key."""
        if not self.adapter: raise MintingError("blockchain adapter is not configured")
        s=self.db.session
        intent=s.query(MintIntent).with_for_update().filter_by(id=intent_id).one_or_none()
        if not intent: raise MintingError("mint intent not found")
        if intent.state == 'CONFIRMED': return intent
        if intent.state in ('SUBMITTED','AMBIGUOUS'):
            receipt=self.adapter.lookup(intent.idempotency_key, intent.tx_hash)
            if not receipt:
                # Never blindly resubmit: without protocol idempotency absence is
                # not proof the first transaction did not land.
                intent.state='AMBIGUOUS'; intent.last_error='submission outcome unresolved; manual reconciliation required'; s.commit(); return intent
        else:
            if intent.attempts >= self.MAX_ATTEMPTS: intent.state='FAILED'; s.commit(); return intent
            intent.attempts += 1; s.commit() # durable attempt marker before side effect
            try: receipt=self.adapter.submit(intent.recipient_address,Decimal(intent.amount),intent.idempotency_key)
            except AmbiguousSubmission as exc:
                intent=s.get(MintIntent,intent.id); intent.state='AMBIGUOUS'; intent.last_error=str(exc)[:2000]; s.commit(); return intent
            except Exception as exc:
                intent=s.get(MintIntent,intent.id); intent.state='FAILED' if intent.attempts>=self.MAX_ATTEMPTS else 'PENDING'; intent.last_error=str(exc)[:2000]; s.commit(); raise
        intent=s.get(MintIntent,intent.id); intent.tx_hash=receipt.tx_hash
        if receipt.confirmed:
            intent.state='CONFIRMED'
        else: intent.state='SUBMITTED'
        intent.last_error=None; s.commit()
        audit_log.append('MINT_STATE_CHANGED','mint-worker',{'intent_id':str(intent.id),'state':intent.state,'tx_hash':intent.tx_hash},intent.audit_trace_id)
        return intent
