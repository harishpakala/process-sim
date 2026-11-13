"""Fail-closed governance verification for approved cross-domain join plans.

Approval records are separate from runtime candidate opt-in. Only an explicitly
verified catalog plan with a matching reviewer record may run without opt-in.
No CLI command here grants approval.
"""
from datetime import date


def require_approval(plan, catalog):
    """Require matching reviewer evidence for every mapping in a verified plan."""
    records = catalog.get("semantic_approvals", [])
    for mapping_id in plan["mapping_ids"]:
        matches = [record for record in records
                   if isinstance(record, dict) and record.get("mapping_id") == mapping_id]
        if len(matches) != 1:
            raise ValueError("Verified mapping lacks a unique semantic approval: " + mapping_id)
        record = matches[0]
        if record.get("decision") != "approved":
            raise ValueError("Semantic approval decision is not approved: " + mapping_id)
        for field in ("reviewer", "approved_at", "rationale", "evidence_reference"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError("Semantic approval missing " + field + ": " + mapping_id)
        try:
            date.fromisoformat(record["approved_at"])
        except ValueError as exc:
            raise ValueError("Semantic approval date must be ISO YYYY-MM-DD") from exc
        if record.get("comparison") != plan.get("comparison"):
            raise ValueError("Semantic approval comparison differs from plan: " + mapping_id)
        if record.get("domains") != plan.get("domains"):
            raise ValueError("Semantic approval domains differ from plan: " + mapping_id)
