"""Experiment 41: one-question, retrieval-first LLM plan, deterministic validation, live mapping, read-only aggregate.

Scope: run-supported engineering functions, AVG of numeric temporal observations, explicit
simulation-time interval. This is not general ontology QA or natural-language time resolution.
No hardcoded function-to-signal routing, no LLM-generated SQL, no benchmark gold in prompt.
"""
import argparse
import json
import math
import os
import re
import sys
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def load(name, path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def parse_plan(raw):
    raw = raw.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, re.I | re.S)
    obj = json.loads(match.group(1) if match else raw)
    if not isinstance(obj, dict) or set(obj) != {"engineering_function", "operation", "data_requirement", "time_basis"}:
        raise ValueError("ABSTAIN: candidate plan has unexpected or missing fields")
    if any(not isinstance(v, str) for v in obj.values()):
        raise ValueError("ABSTAIN: plan values must be strings")
    return obj

def validate_plan(plan, candidates, registry, run_id, start, end):
    from tep_nexus_live_virtual_graph import validate_request
    if plan["engineering_function"] == "ABSTAIN":
        raise ValueError("ABSTAIN: LLM did not identify a supported engineering function")
    if plan["engineering_function"] not in candidates or plan["engineering_function"] not in registry:
        raise ValueError("ABSTAIN: function is not a retrieved and run-supported candidate")
    if plan["operation"] != "AVG":
        raise ValueError("ABSTAIN: only AVG aggregation is supported in this diagnostic")
    if plan["data_requirement"] != "temporal_observations" or plan["time_basis"] != "simulation_time":
        raise ValueError("ABSTAIN: temporal data requirement or time basis unsupported")
    return validate_request(plan["engineering_function"], run_id, start, end, 1)

def aggregate(dsn, request, signal):
    """Read-only, parameterized AVG on ALL rows in the requested interval; no LIMIT."""
    import psycopg
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COUNT(*), AVG(value::double precision)
                       FROM public.signal_samples
                       WHERE run_id = %s::uuid AND signal_id = %s
                         AND simulation_time_hours >= %s
                         AND simulation_time_hours <= %s""",
                    (request["run_id"], signal,
                     request["start_simulation_seconds"] / 3600.0,
                     request["end_simulation_seconds"] / 3600.0))
                count, mean = cur.fetchone()
    if count == 0 or mean is None:
        raise ValueError("ABSTAIN: no historian observations in requested interval")
    if not math.isfinite(float(mean)):
        raise ValueError("ABSTAIN: non-finite historian average")
    return {"observation_count": int(count), "average": float(mean),
            "unit": "not_verified", "aggregation": "AVG(value::double precision)",
            "time_basis": "simulation_time", "interval_inclusive": True}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--question", default="What is the average measured temperature of TI_101 over the last hour?")
    p.add_argument("--run-id", required=True)
    p.add_argument("--start-seconds", type=float, required=True)
    p.add_argument("--end-seconds", type=float, required=True)
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--vector-weight", type=float, default=0.75)
    p.add_argument("--ollama-url", default="http://localhost:11434")
    p.add_argument("--embedding-model", default="nomic-embed-text:latest")
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    p.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    p.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    p.add_argument("--output", type=Path, default=Path("reports/vtkg_end_to_end_41.json"))
    p.add_argument("--no-execute", action="store_true")
    a = p.parse_args()
    if not 1 <= a.top_k <= 100 or not 0 <= a.vector_weight <= 1:
        p.error("Invalid top-k or vector weight")
    sys.path.insert(0, str(ROOT / "scripts"))
    from tep_nexus_function_registry import load_supported_functions, resolve_supported_mapping
    from tep_nexus_live_virtual_graph import validate_request
    request_base = validate_request("placeholder", a.run_id, a.start_seconds, a.end_seconds, 1)
    registry = load_supported_functions(a.mapping_discovery, a.temporal_coverage, request_base["run_id"])
    retrieval = load("exp41_retrieval", HERE / "30_evaluate_simple_questions.py")
    llm = load("exp41_llm", HERE / "33_llm_sparql.py")
    functions = sorted(registry)
    docs = [{"uri": "function:" + f, "function": f, "labels": [f],
             "descriptions": ["Engineering function " + f + " with run-scoped temporal observations"]}
            for f in functions]
    lexical = retrieval.lexical_ranking(a.question, docs)
    vectors = retrieval.embed(a.ollama_url, a.embedding_model,
                              [retrieval.concept_text(d) for d in docs], a.timeout)
    qvec = retrieval.embed(a.ollama_url, a.embedding_model, [a.question], a.timeout)[0]
    vector = retrieval.vector_ranking(qvec, vectors, docs)
    hybrid = retrieval.fusion(lexical, vector, docs, a.vector_weight)
    candidates = [docs[i]["function"] for i in hybrid[:a.top_k]]
    prompt = (
        "Generate a candidate semantic query plan for the engineering question. "
        "Use only the retrieved engineering function candidates. Do not invent signals, "
        "SQL, RDF URIs, run IDs, or measurements. Return exactly a JSON object with "
        "engineering_function (one candidate or ABSTAIN), operation (AVG or UNSUPPORTED), "
        "data_requirement (temporal_observations or UNSUPPORTED), "
        "time_basis (simulation_time or UNSUPPORTED). "
        "The operator has supplied a simulation-time interval separately; interpret the "
        "question for that interval, do not infer wall-clock time. "
        "If the question does not support the operation or time basis, use UNSUPPORTED.\n"
        "Question: " + a.question + "\nRetrieved engineering functions: " +
        json.dumps(candidates) + "\nReturn JSON only."
    )
    report = {"experiment": "41_one_question_vtkg_end_to_end", "question": a.question,
              "run_id": request_base["run_id"],
              "simulation_interval_seconds": [a.start_seconds, a.end_seconds],
              "retrieval": {"lexical": [docs[i]["function"] for i in lexical[:a.top_k]],
                            "vector": [docs[i]["function"] for i in vector[:a.top_k]],
                            "hybrid": candidates},
              "limitations": ["Function-candidate retrieval, not full ontology concept retrieval.",
                              "Only AVG temporal observations supported.",
                              "Operator-supplied simulation interval; no last-wall-clock-hour resolution.",
                              "Mapping remains provisional; physical sensor binding not verified.",
                              "Measurement unit is not verified."]}
    try:
        raw = llm.ollama(a.ollama_url, a.model, prompt, a.timeout)
        report["llm_raw"] = raw
        plan = parse_plan(raw)
        report["candidate_plan"] = plan
        req = validate_plan(plan, candidates, registry, request_base["run_id"], a.start_seconds, a.end_seconds)
        report["validation"] = "passed"
        mapping = resolve_supported_mapping(a.graphdb_url, req["engineering_function"], registry)
        if mapping["engineering_function"] != req["engineering_function"] or mapping["operational_signal"] != registry[req["engineering_function"]]["operational_signal"]:
            raise ValueError("ABSTAIN: live mapping disagrees with run-scoped registry")
        report["validated_mapping"] = mapping
        if a.no_execute:
            report["status"] = "validated_not_executed"
        else:
            dsn = os.environ.get("TEP_TIMESCALE_DSN")
            if not dsn:
                raise ValueError("ABSTAIN: TEP_TIMESCALE_DSN is not configured")
            report["result"] = aggregate(dsn, req, mapping["operational_signal"])
            report["status"] = "executed"
            report["provenance"] = {"mapping": "live GraphDB recheck against run-scoped snapshot",
                                    "historian": "TimescaleDB public.signal_samples",
                                    "physical_sensor_binding": "NOT_VERIFIED"}
    except Exception as exc:
        report["status"] = "abstained_or_failed"
        report["reason"] = str(exc)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
    if report["status"] == "abstained_or_failed":
        sys.exit(2)

if __name__ == "__main__":
    main()
