"""Append-only, hash-chained audit trail (FR-SEC-004, NFR-SEC-002)."""

from nadjet_api.audit.service import AuditTarget, ChainStatus, audit, verify_chain

__all__ = ["AuditTarget", "ChainStatus", "audit", "verify_chain"]
