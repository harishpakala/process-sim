"""Resolve existing AAS asset operational references to historical signals."""
from __future__ import annotations
import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

ASSET_NS = "https://example.org/assetinventory/"
SIGNAL_RE = re.compile(r"(?<![A-Za-z])X(MEAS|MV)[-_]?(\d+)(?!\d)", re.I)

def _signal(reference):
    match = SIGNAL_RE.search(reference)
    if not match:
        return None
    kind, number = match.group(1).upper(), int(match.group(2))
    if not 1 <= number <= (41 if kind == "MEAS" else 12):
        return None
    return "X" + kind + str(number)

def asset_history(asset_iri, run_id, limit=1000):
    from process_sim.api.timeseries import query_samples, query_fault_events
    uid = str(UUID(str(run_id)))
    if not isinstance(asset_iri, str) or not re.fullmatch(r"https?://[A-Za-z0-9._~:/?#@!    if not isinstance(asset_iri, str) or not asset_iri.startswith(ASSET_NS) or not re.fullmatch(r"https://example\\.org/assetinventory/[A-Za-z0-9_./#%-]+", asset_iri):
'()*+,;=%-]+", asset_iri) or len(asset_iri) > 2048:
        raise ValueError("Invalid asset IRI")
        raise ValueError("Invalid AssetInventory asset IRI")
    if not 1 <= limit <= 5000:
        raise ValueError("Limit must be 1..5000")
    query = (
        "SELECT DISTINCT ?reference WHERE { GRAPH ?g { <" + asset_iri + "> "
        "<" + ASSET_NS + "hasOperationalReference> ?reference . } } LIMIT 100"
    )
    endpoint = os.environ.get("GRAPHDB_SPARQL_ENDPOINT", "http://localhost:7200/repositories/AAS")
    req = Request(endpoint, data=urlencode({"query": query}).encode("utf-8"),
                  headers={"Accept": "application/sparql-results+json",
                           "Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urlopen(req, timeout=15) as response:
        bindings = json.load(response)["results"]["bindings"]
    refs = [item["reference"]["value"] for item in bindings]
    signals = sorted(set(filter(None, (_signal(ref) for ref in refs))))
    if len(signals) != 1:
        return {"assetIri": asset_iri, "runId": uid, "references": refs,
                "signals": signals, "status": "unmapped" if not signals else "ambiguous",
                "points": [], "faultEvents": []}
    signal = signals[0]
    points = query_samples(uid, signal, limit)
    # Fault target matching is identifier equality, not inferred physical impact.
    events = [e for e in query_fault_events(uid, 5000)
              if str(e.get("target") or "").upper() == signal]
    return {"assetIri": asset_iri, "runId": uid, "references": refs,
            "signals": signals, "status": "mapped", "signal": signal,
            "points": [{"time": t, "value": v, "observedAt": stamp.isoformat()}
                       for t, v, stamp in points],
            "faultEvents": [
                {"eventId": str(e["event_id"]), "faultId": e["fault_id"],
                 "action": e["action"], "target": e["target"],
                 "observedAt": e["observed_at"].isoformat(),
                 "simulationTimeHours": e["simulation_time_hours"]}
                for e in events]}
