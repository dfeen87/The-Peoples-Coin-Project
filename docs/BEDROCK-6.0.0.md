# Version 6.0.0 — BEDROCK shared-state completion report

## Verified findings and resolution

The v5 report correctly identified that nonce reservations, RBAC sessions,
fraud velocity/freezes, and the plugin audit chain were Python collections.
They are now SQL-backed. Nonce insertion uses a unique key and one transaction;
expired reservations are deleted opportunistically and a nonce remains reserved
for the signature-skew window. Session tokens are stored only as SHA-256 lookup
hashes with durable expiry and revocation. Fraud account locking, window cleanup,
counting, insertion, and automatic freeze occur in one transaction. Validation
still occurs before that transaction, so malformed requests consume no quota.
All protected operations propagate store errors or return denial; there is no
in-memory fallback.

Audit writes use a database transaction and, on PostgreSQL, a transaction-level
advisory lock to impose a single sequence/hash-chain order under concurrency.
JSON is copied and serialized before insertion, reads deserialize fresh values,
and verification recalculates every link and hash. Application code exposes no
update/delete operation. Database permissions should deny those operations to
the runtime role. This is tamper-*evident*, not tamper-proof: a sufficiently
privileged database operator can rewrite rows and hashes. External notarization,
WORM archives, access logging, backups, and organizational controls remain
operator responsibilities.

The reported goodwill-service placeholder was also confirmed. Unverified
submissions now explicitly enter verification rather than pretending to queue a
mint. The circulatory boundary creates one `MintIntent` per verified action and
one `MintOutbox` row in its transaction. The stable key is
`goodwill:<action UUID>`. Outbox publication may be repeated after a crash;
consumers lock and inspect the unique intent. Intent states distinguish
`PENDING`, `SUBMITTED`, `CONFIRMED`, `FAILED`, and `AMBIGUOUS`. A durable attempt
marker is committed before submission. Submitted/ambiguous work is reconciled
through adapter lookup and is not blindly re-submitted when lookup is
inconclusive. Confirmation must come from an adapter receipt; queue acceptance
or transaction submission is not confirmation.

No contract address, credential, or live transaction was used. Exactly-once
chain effects are **not** claimed. Safe automated crash recovery requires the
configured adapter and deployed contract/protocol to enforce or query the
idempotency key. Without that facility the intent remains `AMBIGUOUS` for manual
reconciliation.

## Transactions, retention, and cleanup

* UTC Unix seconds are used for security expiry/window comparisons; mint/audit
  database timestamps are UTC-aware.
* Nonces expire after the configured (default 300-second) signature window and
  are opportunistically removed. A scheduled delete may reclaim old rows.
* Velocity events older than 60 seconds are removed during accepted checks.
* Expired/revoked session rows should be retained according to the security
  investigation policy, then removed by an operator job.
* Audit rows have no application deletion path or automatic expiry. Operators
  must select and document retention and backup/WORM export rules.
* PostgreSQL is required for multi-host production consistency. SQLite is a
  durable single-host development/test option only.

## Deployment and migration

Release 6.0.0 is a major version because a shared database and new worker/adapter
contract are mandatory. Set `BANKING_STATE_DATABASE_URL` to the shared
PostgreSQL URL, set `BANKING_AUTO_CREATE=false`, apply `alembic upgrade head`,
then deploy web, outbox dispatcher, and mint workers. Grant the runtime role
insert/select access needed for audit evidence but no audit update/delete.
Configure a durable broker and an adapter capable of idempotency lookup before
enabling mint dispatch.

The downgrade removes nonce/session/fraud/audit evidence and all outstanding
mint recovery state. It must not be run until that data has been exported and
its regulatory/operational retention disposition approved. A rolling downgrade
to v5 is unsafe because v5 workers neither understand the outbox nor share
security state.

## Verification status

Repository behavioral tests cover independent store clients, restart-visible
session expiry/revocation, concurrent nonce winners, atomic velocity and freeze,
audit ownership/restart/concurrent ordering, malformed-input preservation, and
existing banking routes. Mint service boundaries are deterministic and designed
for adapter fakes; no external-chain integration is represented as validated.
CI provisions PostgreSQL 16 and runs compileall plus the complete pytest suite
before deployment.

In this implementation environment `python -m pip install -r
requirements-dev.txt` was attempted but the package index tunnel returned HTTP
403, so dependencies could not be installed. The subsequent full pytest attempt
collected three modules and stopped with three import errors (`flask` absent);
there is therefore no claimed passing local suite. The workflow definition is
not evidence of a passing hosted run. PostgreSQL, broker delivery, a deployed
contract, chain confirmations, IAM, backup restore, external notarization, and
live crash injection remain unverified external dependencies.
