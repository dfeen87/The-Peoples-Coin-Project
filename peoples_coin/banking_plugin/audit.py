"""Durable append-only hash-chain audit evidence.

The chain detects database changes; it is not external notarization and a database
administrator able to rewrite both records and hashes remains in the trust model.
"""
import copy
import hashlib
import json
import time
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from .store import security_store

class MerkleTree:
    @staticmethod
    def hash_entry(entry):
        return hashlib.sha256(json.dumps(entry, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    @classmethod
    def compute_root(cls, hashes):
        if not hashes: return hashlib.sha256(b'').hexdigest()
        level = list(hashes)
        while len(level) > 1:
            if len(level) % 2: level.append(level[-1])
            level = [hashlib.sha256((level[i]+level[i+1]).encode()).hexdigest() for i in range(0,len(level),2)]
        return level[0]

class TamperEvidentAuditLog:
    def __init__(self, store=None): self.store = store or security_store
    def append(self, event_type: str, actor: str, context: Dict[str,Any], trace_id: Optional[str]=None):
        owned = copy.deepcopy(context)
        payload = json.dumps(owned, sort_keys=True, separators=(',', ':'))
        now = time.time()
        with self.store.transaction(immediate=True) as conn:
            if conn.dialect.name == 'postgresql':
                # Serialize this one global chain even when it is initially
                # empty (there is then no row for SELECT FOR UPDATE to lock).
                conn.execute(text("SELECT pg_advisory_xact_lock(1347374164)"))
            last = conn.execute(text("SELECT sequence,entry_hash FROM banking_audit_entries ORDER BY sequence DESC LIMIT 1")).first()
            previous = last.entry_hash if last else '0'*64
            index = int(last.sequence) if last else 0
            entry = {'index': index, 'timestamp': now, 'event_type': event_type, 'actor': actor, 'context': owned, 'trace_id': trace_id, 'previous_hash': previous}
            digest = MerkleTree.hash_entry(entry)
            sequence = conn.execute(text("INSERT INTO banking_audit_entries(timestamp,event_type,actor,context_json,trace_id,previous_hash,entry_hash) VALUES (:t,:e,:a,:c,:r,:p,:h) RETURNING sequence"), {'t':now,'e':event_type,'a':actor,'c':payload,'r':trace_id,'p':previous,'h':digest}).scalar_one()
        entry['index'] = sequence - 1
        # hash used provisional index equals previous sequence, which is sequence-1.
        entry['hash'] = digest
        return copy.deepcopy(entry)
    def get_entries(self, limit=100):
        if isinstance(limit,bool) or not isinstance(limit,int) or limit < 0: raise ValueError("limit must be a non-negative integer")
        if not limit: return []
        with self.store.transaction() as conn:
            rows=conn.execute(text("SELECT * FROM banking_audit_entries ORDER BY sequence DESC LIMIT :n"), {'n':limit}).mappings().all()[::-1]
        return [{'index':r['sequence']-1,'timestamp':r['timestamp'],'event_type':r['event_type'],'actor':r['actor'],'context':json.loads(r['context_json']),'trace_id':r['trace_id'],'previous_hash':r['previous_hash'],'hash':r['entry_hash']} for r in rows]
    def verify_integrity(self):
        with self.store.transaction() as conn: rows=conn.execute(text("SELECT * FROM banking_audit_entries ORDER BY sequence")).mappings().all()
        previous='0'*64
        for i,r in enumerate(rows):
            entry={'index':i,'timestamp':r['timestamp'],'event_type':r['event_type'],'actor':r['actor'],'context':json.loads(r['context_json']),'trace_id':r['trace_id'],'previous_hash':r['previous_hash']}
            if r['sequence'] != i+1 or r['previous_hash'] != previous or MerkleTree.hash_entry(entry) != r['entry_hash']: return False
            previous=r['entry_hash']
        return True
    def get_merkle_root(self): return MerkleTree.compute_root([e['hash'] for e in self.get_entries(2**31-1)])
    def get_snapshot(self):
        entries=self.get_entries(2**31-1)
        return {'total_records':len(entries),'merkle_root':MerkleTree.compute_root([e['hash'] for e in entries]),'timestamp':time.time(),'latest_entry_hash':entries[-1]['hash'] if entries else '0'*64}

audit_log=TamperEvidentAuditLog()
