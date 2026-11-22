"""HTTP adapter for the existing constrained TEP NEXUS VTKG CLI.

No new planner, mapping inference, SQL, or RDF materialization.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]


class VtkgUnavailable(RuntimeError):
    pass


def run_question(payload: dict, *, runner=subprocess.run, environ=None):
    env = os.environ if environ is None else environ
    if not isinstance(payload, dict) or set(payload) != {
        "question", "engineering_function", "run_id",
        "start_simulation_seconds", "end_simulation_seconds", "limit"
    }:
        raise ValueError("VTKG requires question, engineering_function, run_id, start_simulation_seconds, end_simulation_seconds and limit")
    question = payload["question"]
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")
    # Use the already-tested validator; no heuristic parsing of time/function.
    scripts = ROOT / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        from tep_nexus_live_virtual_graph import validate_request
        req = validate_request(payload["engineering_function"], payload["run_id"],
                               payload["start_simulation_seconds"],
                               payload["end_simulation_seconds"], payload["limit"])
    finally:
        sys.path.remove(str(scripts))
    dsn = env.get("TEP_TIMESCALE_DSN")
    graphdb = env.get("GRAPHDB_SPARQL_ENDPOINT")
    if not dsn or not graphdb:
        raise VtkgUnavailable("Configure TEP_TIMESCALE_DSN and GRAPHDB_SPARQL_ENDPOINT")
    cli = scripts / "tep_nexus_unified_virtual_query.py"
    if not cli.is_file():
        raise VtkgUnavailable("Existing VTKG query CLI is unavailable")
    with tempfile.TemporaryDirectory(prefix="tep-vtkg-") as tmp:
        output = Path(tmp) / "result.json"
        args = [sys.executable, str(cli), "--question", question.strip(),
                "--function", req["engineering_function"], "--run-id", req["run_id"],
                "--start-seconds", str(req["start_simulation_seconds"]),
                "--end-seconds", str(req["end_simulation_seconds"]),
                "--limit", str(req["limit"]), "--graphdb-url", graphdb,
                "--output", str(output)]
        try:
            completed = runner(args, cwd=str(ROOT), env=dict(env),
                               capture_output=True, text=True, timeout=180, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VtkgUnavailable("VTKG query process failed or timed out") from exc
        if completed.returncode != 0:
            logging.error("VTKG CLI exited %s; stderr: %s", completed.returncode,
                          (completed.stderr or "")[-6000:])
            raise VtkgUnavailable("VTKG query rejected or failed; inspect backend logs")
        try:
            report = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise VtkgUnavailable("VTKG CLI returned no valid report") from exc
    if (not isinstance(report, dict) or report.get("materializedInGraphDB") is not False
            or not isinstance(report.get("evidence"), dict)
            or not isinstance(report["evidence"].get("observations"), list)
            or not isinstance(report.get("validatedPlan"), dict)):
        raise VtkgUnavailable("VTKG CLI returned unexpected evidence")
    return report


def discover_functions(run_id: str, *, environ=None):
    """Discover run-supported engineering functions, rechecked against live GraphDB.

    Reuses the existing evidence-gated registry and live resolver. No inferred
    mappings or unverified GraphDB functions are offered as executable queries.
    """
    from uuid import UUID
    env = os.environ if environ is None else environ
    graphdb = env.get("GRAPHDB_SPARQL_ENDPOINT")
    if not graphdb:
        raise VtkgUnavailable("Configure GRAPHDB_SPARQL_ENDPOINT")
    normalized_run = str(UUID(str(run_id)))
    scripts = ROOT / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        from tep_nexus_function_registry import load_supported_functions, resolve_supported_mapping
        registry = load_supported_functions(
            ROOT / "reports/tep_nexus_mapping_discovery.json",
            ROOT / "reports/tep_nexus_temporal_coverage.json",
            normalized_run,
        )
        functions = []
        rejected_functions = []
        for function in sorted(registry):
            try:
                functions.append(resolve_supported_mapping(graphdb, function, registry))
            except RuntimeError as exc:
                # Only isolate known mapping-validation rejections. Transport and
                # unexpected errors must still fail the request, not look like
                # an empty or partially verified GraphDB result.
                reason = str(exc)
                if reason not in (
                    "GraphDB mapping missing or ambiguous for selected function",
                    "GraphDB mapping changed since discovery; regenerate reports",
                ):
                    raise
                rejected_functions.append({"engineering_function": function, "reason": reason})
    finally:
        sys.path.remove(str(scripts))
    return {"run_id": normalized_run, "functions": functions,
            "rejected_functions": rejected_functions,
            "source": "GraphDB AAS live resolution + run-scoped evidence-gated registry",
            "mappingConfidence": "PROVISIONAL",
            "physicalSensorBinding": "NOT_VERIFIED",
            "sharedRunProvenance": "NOT_VERIFIED"}


def discover_historian_runs(*, environ=None):
    """Run IDs come from the actual historian, not the provisional registry."""
    from uuid import UUID
    import psycopg
    env = os.environ if environ is None else environ
    dsn = env.get("TEP_TIMESCALE_DSN")
    if not dsn:
        raise VtkgUnavailable("Configure TEP_TIMESCALE_DSN")
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT run_id FROM public.signal_samples ORDER BY run_id")
                runs = [str(UUID(str(row[0]))) for row in cur.fetchall()]
    return {"runs": runs}


def discover_historian_functions(run_id, *, domain="DEXPI", environ=None):
    """Only offer unique live DEXPI/OPCUA mappings with run-scoped samples."""
    from uuid import UUID
    import psycopg
    import requests
    env = os.environ if environ is None else environ
    dsn = env.get("TEP_TIMESCALE_DSN")
    graphdb = env.get("GRAPHDB_SPARQL_ENDPOINT")
    if not dsn or not graphdb:
        raise VtkgUnavailable("Configure TEP_TIMESCALE_DSN and GRAPHDB_SPARQL_ENDPOINT")
    if domain not in ("DEXPI", "ECAD"):
        raise ValueError("Unsupported engineering domain")
    run = str(UUID(str(run_id)))
    query = """
PREFIX dexpi: <https://example.org/dexpi/>
PREFIX opcua: <https://example.org/opcuaconnectivity/>
SELECT DISTINCT ?localId ?assetIdentifier ?signalName WHERE {
 GRAPH ?dg {
  ?function a dexpi:InstrumentationFunction ;
            dexpi:hasLocalId ?localId ;
            dexpi:hasAssetIdentifier ?assetIdentifier .
 }
 GRAPH ?og {
  ?mapping opcua:hasAssetIdentifier ?assetIdentifier ;
           opcua:hasSignalName ?signalName .
 }
} ORDER BY ?localId ?signalName
"""
    if domain == "ECAD":
        query = """
PREFIX ecad: <https://example.org/ecad/>
PREFIX opcua: <https://example.org/opcuaconnectivity/>
SELECT DISTINCT ?localId ?assetIdentifier ?signalName WHERE {
 GRAPH ?eg {
  ?component ecad:hasLocalId ?localId ;
             ecad:hasAssetIdentifier ?assetIdentifier .
 }
 GRAPH ?og {
  ?mapping opcua:hasAssetIdentifier ?assetIdentifier ;
           opcua:hasSignalName ?signalName .
 }
} ORDER BY ?localId ?signalName
"""
    response = requests.post(graphdb, data={"query": query},
                             headers={"Accept": "application/sparql-results+json"}, timeout=30)
    response.raise_for_status()
    grouped = {}
    for row in response.json()["results"]["bindings"]:
        function = row["localId"]["value"].strip()
        if domain == "ECAD":
            import re
            if not re.fullmatch(r"(?:FI|LI|PI|TI)-[0-9]+", function):
                continue
        pair = (row["assetIdentifier"]["value"].strip(), row["signalName"]["value"].strip())
        grouped.setdefault(function, set()).add(pair)
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute("""SELECT signal_id, COUNT(*) FROM public.signal_samples
                               WHERE run_id = %s::uuid GROUP BY signal_id""", (run,))
                counts = dict(cur.fetchall())
    functions = []
    rejected = []
    for function, mappings in sorted(grouped.items()):
        if len(mappings) != 1:
            rejected.append({"engineering_function": function, "reason": "Ambiguous live semantic mapping"})
            continue
        asset, signal = next(iter(mappings))
        if not asset or not signal or counts.get(signal, 0) <= 0:
            rejected.append({"engineering_function": function, "reason": "No matching run-scoped observations or incomplete mapping"})
            continue
        functions.append({"engineering_function": function, "operational_signal": signal,
                          "asset_identifier": asset, "sample_count": counts[signal]})
    return {"run_id": run, "functions": functions, "rejected_functions": rejected,
            "domain": domain, "source": f"live GraphDB {domain}/OPCUAConnectivity + TimescaleDB"}


def run_historian_question(payload, *, environ=None):
    """Execute the independently validated DEXPI historian path, without Ollama."""
    from uuid import UUID
    env = os.environ if environ is None else environ
    if not isinstance(payload, dict) or set(payload) != {
        "question", "engineering_function", "run_id",
        "start_simulation_seconds", "end_simulation_seconds", "domain"
    }:
        raise ValueError("Expected question, engineering_function, run_id and optional time fields")
    if not isinstance(payload["question"], str) or not 5 <= len(payload["question"].strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")
    domain = payload["domain"]
    if domain not in ("DEXPI", "ECAD"):
        raise ValueError("Unsupported engineering domain")
    dsn = env.get("TEP_TIMESCALE_DSN")
    graphdb = env.get("GRAPHDB_SPARQL_ENDPOINT")
    if not dsn or not graphdb:
        raise VtkgUnavailable("Configure TEP_TIMESCALE_DSN and GRAPHDB_SPARQL_ENDPOINT")
    scripts = ROOT / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        from tep_nexus_dexpi_historian import execute
        result = execute(payload["question"].strip(), payload["engineering_function"],
                       str(UUID(str(payload["run_id"]))), dsn, graphdb,
                       payload["start_simulation_seconds"], payload["end_simulation_seconds"],
                       domain=domain)
        try:
            from tep_nexus_virtual_graph import project
            from tep_nexus_live_virtual_graph import observation_primary_key, observation_fingerprint
            from datetime import datetime
            mapping = dict(result["mapping"], domain=domain)
            samples = []
            seen = set()
            for sample in result["observations"]:
                stamp = datetime.fromisoformat(sample["observedAt"])
                if stamp.tzinfo is None or stamp.utcoffset() is None:
                    raise ValueError("Observation timestamp lacks timezone")
                key = observation_primary_key(result["runId"], mapping["operational_signal"], stamp)
                if key in seen:
                    raise ValueError("Duplicate observation source key")
                seen.add(key)
                samples.append(dict(sample, observationPrimaryKeyHash=key,
                    observationFingerprint=observation_fingerprint(result["runId"],
                        mapping["operational_signal"], sample["simulationTimeHours"], sample["value"], stamp)))
            graph = project({
                "validatedPlan": {"engineering_function": result["engineeringFunction"]},
                "engineeringMapping": mapping,
                "temporalEvidence": {"runId": result["runId"], "signal": mapping["operational_signal"],
                    "faultCommands": [], "windows": [{"samples": samples, "truncated": result["truncated"]}]},
            })
            if sum(n["type"] == "VirtualObservation" for n in graph["nodes"]) != result["observationCount"]:
                raise ValueError("Graph observation count mismatch")
            graph["snapshotScope"] = "single historian response; no additional retrieval"
            graph["request"] = {k: result[k] for k in ("domain", "engineeringFunction", "runId",
                "startSimulationSeconds", "endSimulationSeconds", "retrievedAtUtc")}
            graph["capabilities"] = {"R01": bool(samples), "R02": False, "R03": False,
                                     "R04": False, "R05": False}
            result["vtkg"] = graph
            result["vtkgStatus"] = "constructed"
        except Exception:
            logging.exception("Historian VTKG construction failed")
            result["vtkgStatus"] = "unavailable"
        return result
    finally:
        sys.path.remove(str(scripts))


def run_semantic_join_question(payload, *, environ=None):
    """Read-only semantic join, without historian access or NL model execution."""
    import re
    env = os.environ if environ is None else environ
    if not isinstance(payload, dict) or set(payload) != {"question", "engineering_function", "domain"}:
        raise ValueError("Expected question, engineering_function and domain")
    question, function, domain = payload["question"], payload["engineering_function"], payload["domain"]
    if domain not in ("DEXPI", "ECAD") or not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Invalid semantic query")
    if not isinstance(function, str):
        raise ValueError("Invalid LocalId")
    ids = {v.upper() for v in re.findall(r"(?<![A-Za-z0-9_-])[A-Za-z]{2}[_-][0-9]+(?![A-Za-z0-9_-])", question)}
    if ids != {function.upper()}:
        raise ValueError("Question and requested engineering function must agree")
    if "signalname" not in question.lower() or "timescaledb" in question.lower() or "recorded values" in question.lower():
        raise ValueError("Semantic-only question must request SignalName without historian retrieval")
    endpoint = env.get("GRAPHDB_SPARQL_ENDPOINT")
    if not endpoint:
        raise VtkgUnavailable("Configure GRAPHDB_SPARQL_ENDPOINT")
    scripts = ROOT / "scripts"
    sys.path.insert(0, str(scripts))
    try:
        from tep_nexus_dexpi_historian import resolve_signal
        mapping = resolve_signal(endpoint, function.upper(), domain=domain)
    finally:
        sys.path.remove(str(scripts))
    return {"domain": domain, "engineeringFunction": function.upper(),
            "signalName": mapping["operational_signal"],
            "mapping": mapping, "mode": "semantic_only", "historianQueried": False}
