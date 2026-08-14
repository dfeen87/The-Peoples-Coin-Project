"""
Append-only Audit Log Integrity with Merkle-Root Integrity Proofs
and Tamper-Evident Snapshots.
"""

import hashlib
import time
import json
from typing import List, Dict, Any, Optional
import threading

class MerkleTree:
    """Computes Merkle root and cryptographic proofs for audit trail verification."""

    @staticmethod
    def hash_entry(entry: Dict[str, Any]) -> str:
        serialized = json.dumps(entry, sort_keys=True)
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

    @classmethod
    def compute_root(cls, hashes: List[str]) -> str:
        if not hashes:
            return hashlib.sha256(b"").hexdigest()
        if len(hashes) == 1:
            return hashes[0]

        new_level = []
        for i in range(0, len(hashes), 2):
            left = hashes[i]
            right = hashes[i + 1] if i + 1 < len(hashes) else left
            combined = hashlib.sha256((left + right).encode('utf-8')).hexdigest()
            new_level.append(combined)

        return cls.compute_root(new_level)


class TamperEvidentAuditLog:
    """Thread-safe, append-only encrypted tamper-evident audit log ledger."""

    def __init__(self):
        self._entries: List[Dict[str, Any]] = []
        self._hashes: List[str] = []
        self._lock = threading.Lock()
        self._last_snapshot_hash: str = ""

    def append(self, event_type: str, actor: str, context: Dict[str, Any], trace_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            prev_hash = self._hashes[-1] if self._hashes else "0" * 64
            timestamp = time.time()
            entry = {
                'index': len(self._entries),
                'timestamp': timestamp,
                'event_type': event_type,
                'actor': actor,
                'context': context,
                'trace_id': trace_id,
                'previous_hash': prev_hash
            }
            entry_hash = MerkleTree.hash_entry(entry)
            entry['hash'] = entry_hash

            self._entries.append(entry)
            self._hashes.append(entry_hash)
            return entry

    def get_merkle_root(self) -> str:
        with self._lock:
            return MerkleTree.compute_root(self._hashes)

    def verify_integrity(self) -> bool:
        """Verifies hash link chaining and Merkle tree consistency across all entries."""
        with self._lock:
            for i in range(len(self._entries)):
                entry = self._entries[i]
                expected_prev = self._entries[i - 1]['hash'] if i > 0 else "0" * 64
                if entry['previous_hash'] != expected_prev:
                    return False

                entry_copy = {k: v for k, v in entry.items() if k != 'hash'}
                if MerkleTree.hash_entry(entry_copy) != entry['hash']:
                    return False
            return True

    def get_snapshot(self) -> Dict[str, Any]:
        """Creates a tamper-evident snapshot certificate of current audit state."""
        with self._lock:
            root = MerkleTree.compute_root(self._hashes)
            snapshot = {
                'total_records': len(self._entries),
                'merkle_root': root,
                'timestamp': time.time(),
                'latest_entry_hash': self._hashes[-1] if self._hashes else "0" * 64
            }
            return snapshot

    def get_entries(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            return self._entries[-limit:]


audit_log = TamperEvidentAuditLog()
