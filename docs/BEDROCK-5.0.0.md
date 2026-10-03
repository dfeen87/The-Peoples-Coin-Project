# Version 5.0.0 BEDROCK Engineering Report

## Release decision

Version 5.0.0 is the next major project baseline after 4.1.0. The existing
Flask blueprint, service, SQLAlchemy model, system-controller, and read-only
observability architecture remains in place. The major increment records
deliberate behavioral-contract changes at banking trust boundaries; it does not
claim that every public Python API changed or that the prior architecture was
fundamentally defective.

## Architecture and data flow reviewed

The main application factory configures persistence, Flask extensions, optional
Celery/Redis integration, biological-system services, consensus, and API
blueprints. Routes authenticate and validate requests before service methods use
SQLAlchemy session scopes to commit durable state. The optional banking plugin
adds in-process RBAC sessions, fraud velocity/freeze state, signed-request nonce
state, a tamper-evident audit chain, PCI screening, and trace lineage. The
separate observability application exposes database and host snapshots through
GET-only endpoints. Docker, Cloud Build, Kubernetes manifests, migrations, and
GitHub Actions form the build and deployment boundary.

## Invariant map and confirmed defects

| Behavior | Required invariant | Previous enforcement/test | v5 enforcement |
| --- | --- | --- | --- |
| HMAC verification | timestamps are finite and each nonce succeeds at most once | skew and replay checks existed; non-finite and concurrency boundaries were untested | non-finite timestamps fail closed; nonce check/reservation is process-thread atomic; regression coverage added |
| Fraud assessment | amounts are finite and non-negative; hours are 0–23; rejection does not consume velocity | route coercion allowed NaN, infinity, negative amounts, invalid hours, and coercion exceptions | complete domain validation occurs before velocity mutation; direct engine validation and regression coverage added |
| RBAC provisioning | only an already-authorized administrator may grant roles | the public POST endpoint anonymously issued every role, including admin | POST requires a valid session with admin permission; anonymous and customer escalation tests added |
| Audit append/read | callers cannot mutate committed audit evidence; entry and Merkle hash indexes agree | mutable context and returned entries aliased internal state; the parallel hash index was not verified | deep-copy ownership boundaries and hash-index verification added with regression coverage |
| CI | all collected tests execute before deployable changes merge | deployment workflow built and pushed without running tests | dedicated Python 3.11 workflow compiles sources and runs the complete pytest suite using declared test dependencies |
| Version reporting | active surfaces report one authoritative release | source, badge, and observability docs reported 4.1.0 | active metadata reports 5.0.0; historical 4.1.0 notes remain historical |
| Deployment secrets | credentials never live in tracked manifests or build arguments | Cloud Build contained a database password and Kubernetes manifests embedded a broker URL | tracked credentials were removed; runtime configuration must use Cloud Run settings/Secret Manager and Kubernetes `secretKeyRef` |

The first four rows were previously implicit or incompletely tested invariants.
They follow directly from the plugin's documented strict fail-closed contract.

## Failure, state, trust, and contract changes

Malformed numeric fraud requests now return `400 INVALID_FRAUD_REQUEST` before
recording activity. Previously, conversion failures could become 500 responses,
while NaN, infinity, negative amounts, and out-of-range hours could enter scoring
and sometimes receive an allow recommendation. Invalid HMAC timestamps now return
`401 INVALID_SIGNATURE`. RBAC session creation now returns 401/403 unless an
existing administrator authorizes it; trusted deployment code may still
bootstrap sessions through the existing `RBACManager` integration API.

Audit append and read methods now transfer copies rather than references. This
preserves the append-only evidence contract after successful calls. Integrity
verification also checks the internal Merkle hash input list against every
stored entry. These are ownership and verification corrections, not a new audit
architecture. State remains process-local, as it was before this release.

## Regression tests

The banking suite now proves anonymous and lower-role privilege escalation is
rejected, invalid numeric requests do not alter velocity state, NaN timestamps
cannot authenticate, external context/return-value mutation cannot rewrite audit
evidence, and hash-index corruption is detected. Existing happy-path, PCI,
freeze, MFA, signature, trace, audit, and observability tests remain enabled.

## CI and dependency behavior

CI uses Python 3.11, installs the locked runtime set plus the explicitly declared
pytest version, byte-compiles application and test modules, and executes pytest
without test-path filtering. Deployment remains a separate workflow. Redis,
Kubernetes, RabbitMQ, Firebase, PostgreSQL, and Google Cloud are still external
integration surfaces; unit tests do not certify those services or their IAM and
network configuration.

## Compatibility and rejected legacy behavior

This project uses the major number as an engineering baseline and also includes
real behavioral incompatibilities. Anonymous privileged RBAC provisioning,
non-finite or negative fraud amounts, out-of-range fraud hours, and non-finite
signature timestamps are now rejected because accepting them violates the
documented fail-closed trust model. Valid signatures, role inspection, authorized
provisioning, ordinary fraud assessment, PCI checks, and existing endpoint shapes
are preserved.

## Risks investigated but not changed

Consensus chain replacement and ledger reconstruction contain explicit
not-implemented markers. Activating those paths could discard chain/ledger data,
so they require a separately designed persistence migration and were not
speculatively completed in this focused pass. In-memory banking state is not
shared across Gunicorn workers and is not durable across restarts. The current
audit structure proves process-local consistency, not external notarization or
durable regulatory retention. Historical/backup migrations and generated cloud
resource metadata were left unchanged because they describe prior state rather
than active release metadata.

## Remaining validation requirements

Software tests are not financial, PCI-DSS, FINRA, FDIC, security, or production
certification. Before real-world use, operators must perform PostgreSQL migration
and rollback drills, multi-worker/shared-state design validation, Redis failure
and retry testing, queue idempotency testing, concurrency and load testing,
external penetration review, key-management and rotation review, durable audit
retention/notarization design, cloud IAM review, disaster recovery exercises,
and applicable independent compliance assessment. Related external services were
not available as source repositories during this audit, so compatibility is
limited to the adapters and declared dependency versions present here.

Because a database credential existed in Git history, operators must rotate it
even though it is absent from the v5 tree. They must likewise replace any broker
guest credential previously deployed and populate the `RABBITMQ_URL` key in the
`peoples-coin-secrets` Kubernetes Secret before applying the updated manifests.
