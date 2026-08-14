"""
Peoples Coin Traditional Banking Security Plugin.
Provides banking-grade security capabilities including Dual HMAC request signing,
Strict RBAC with hardware-bound MFA tokens, PCI-DSS data controls,
Velocity checks & anomaly scoring fraud triggers, tamper-evident Merkle audit logs,
and FINRA/FDIC event tracing.
"""

from .pci import pci_manager, PCIDataManager
from .rbac import rbac_manager, require_role, RBACManager
from .audit import audit_log, MerkleTree, TamperEvidentAuditLog
from .fraud import fraud_engine, FraudEngine
from .tracing import regulated_tracer, RegulatedTracer
from .middleware import banking_security_middleware, RequestSigner
from .routes import banking_plugin_blueprint

__all__ = [
    "pci_manager",
    "PCIDataManager",
    "rbac_manager",
    "require_role",
    "RBACManager",
    "audit_log",
    "MerkleTree",
    "TamperEvidentAuditLog",
    "fraud_engine",
    "FraudEngine",
    "regulated_tracer",
    "RegulatedTracer",
    "banking_security_middleware",
    "RequestSigner",
    "banking_plugin_blueprint",
]
