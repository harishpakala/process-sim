"""Evidence-preserving engineering-to-temporal workflow.

The existing asset_history service is authoritative for GraphDB operational
references and TimescaleDB signal retrieval. No new identity joins are inferred.
"""

# Created: 2026-10-23
# Author: Harish
from __future__ import annotations

from .temporal_plan import validate_temporal_plan, execute_temporal_plan


def execute_asset_signal_workflow(plan, *, asset_reader=None):
    """Execute the existing validated asset-history join with an audit trail."""
    validated = validate_temporal_plan(plan)
    if validated["operation"] != "asset_history":
        raise ValueError("Workflow requires asset_history operation")
    output = execute_temporal_plan(validated, asset_reader=asset_reader)
    evidence = output["result"]
    if not isinstance(evidence, dict):
        raise ValueError("Unexpected asset-history response")
    status = evidence.get("status")
    if status not in ("mapped", "unmapped", "ambiguous"):
        raise ValueError("Unknown mapping status")
    signal = evidence.get("signal") if status == "mapped" else None
    if status == "mapped" and (not signal or signal not in evidence.get("signals", [])):
        raise ValueError("Mapped result lacks corroborating signal identifier")
    return {
        "status": "executed_unverified" if status == "mapped" else "insufficient_mapping",
        "workflow": "engineering_asset_to_timeseries",
        "runId": validated["runId"],
        "assetIri": validated["assetIri"],
        "mappingStatus": status,
        "signal": signal,
        "points": evidence.get("points", []) if status == "mapped" else [],
        "faultEvents": evidence.get("faultEvents", []) if status == "mapped" else [],
        "evidence": {
            "operationalReferences": evidence.get("references", []),
            "signalCandidates": evidence.get("signals", []),
            "source": "GraphDB operational reference + TimescaleDB",
            "interpretation": "Identifier-based mapping; no claim of physical installation or fault causality.",
        },
    }
