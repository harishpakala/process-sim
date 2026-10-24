"""Bounded temporal query protocol backed by existing TimescaleDB APIs."""
from __future__ import annotations
from uuid import UUID
from process_sim.api.timeseries import query_samples, query_runs
from process_sim.api.asset_history import asset_history

def validate_temporal_plan(plan):
    if not isinstance(plan, dict):
        raise ValueError("Plan must be an object")
    op = plan.get("operation")
    fields = {"runs": {"operation", "limit"},
              "signal_history": {"operation", "runId", "signal", "limit"},
              "asset_history": {"operation", "runId", "assetIri", "limit"}}
    if op not in fields or set(plan) != fields[op]:
        raise ValueError("Unsupported operation or fields")
    limit = plan["limit"]
    if type(limit) is not int or not 1 <= limit <= (500 if op == "runs" else 5000):
        raise ValueError("Invalid limit")
    normalized = dict(plan)
    if op != "runs":
        try:
            normalized["runId"] = str(UUID(plan["runId"]))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("Invalid runId") from exc
    if op == "signal_history":
        import re
        if not isinstance(plan["signal"], str) or not re.fullmatch(
            r"XMEAS(?:[1-9]|[1-3][0-9]|4[01])|XMV(?:[1-9]|1[0-2])", plan["signal"]
        ):
            raise ValueError("Invalid signal")
    if op == "asset_history":
        import re
        asset = plan["assetIri"]
        if not isinstance(asset, str) or not 1 <= len(asset) <= 2048 or not re.fullmatch(
            r"https?://[A-Za-z0-9._~:/?#@!$&()*+,;=%-]+", asset
        ):
            raise ValueError("Invalid asset IRI")
    return normalized

def execute_temporal_plan(plan, *, runs_reader=None, samples_reader=None, asset_reader=None):
    p = validate_temporal_plan(plan)
    op = p["operation"]
    if op == "runs":
        return {"operation": op, "source": "TimescaleDB",
                "runs": (runs_reader or query_runs)(p["limit"])}
    if op == "asset_history":
        return {"operation": op, "source": "GraphDB operational reference + TimescaleDB",
                "result": (asset_reader or asset_history)(p["assetIri"], p["runId"], p["limit"]),
                "note": "Operational reference does not establish physical installation."}
    points = (samples_reader or query_samples)(p["runId"], p["signal"], p["limit"])
    return {"operation": op, "source": "TimescaleDB", "runId": p["runId"],
            "signal": p["signal"],
            "points": [{"simulationTimeHours": t, "value": v,
                        "observedAt": observed.isoformat()} for t, v, observed in points]}
