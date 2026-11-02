"""Read-only two-function semantic/temporal comparison research prototype.

LLM plans and explains; deterministic code validates identifiers, resolves
mappings, computes comparisons and checks explicit narrative evidence coverage.
"""
import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

from tep_nexus_function_registry import load_supported_functions, resolve_supported_mapping
from tep_nexus_ollama_query_planner import ollama_chat, utc_now
from tep_nexus_semantic_temporal_live import retrieve_temporal_context
from tep_nexus_temporal_analytics import summarize_history
from tep_nexus_comparison_answer_validation import validate_comparison_answer
from tep_nexus_structured_answer import structured_prompt, validate_structured_answer


def validate_comparison_plan(plan, question, registry):
    if not isinstance(plan, dict) or set(plan) != {"engineering_functions", "history_window_minutes"}:
        raise ValueError("Comparison plan requires exactly engineering_functions and history_window_minutes")
    functions = plan["engineering_functions"]
    if (not isinstance(functions, list) or len(functions) != 2
            or any(not isinstance(x, str) for x in functions)
            or len(set(functions)) != 2):
        raise ValueError("Exactly two distinct engineering functions required")
    mentioned = {x.upper() for x in re.findall(r"\b[A-Za-z]{2}_\d+\b", question, re.I)}
    if mentioned != set(functions):
        raise ValueError("Comparison plan does not match the two explicitly requested functions")
    if any(x not in registry for x in functions):
        raise ValueError("Unsupported engineering function in comparison")
    minutes = plan["history_window_minutes"]
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not math.isfinite(minutes) or not 0 < minutes <= 120:
        raise ValueError("Comparison window must be between 0 and 120 simulation minutes")
    duration = re.search(r"\b(?:last|past|previous|over the last)\s+(\d+)\s+(?:simulation\s+)?(minutes?|hours?)\b", question, re.I)
    if duration:
        expected = int(duration.group(1)) * (60 if duration.group(2).lower().startswith("hour") else 1)
        if abs(minutes - expected) > 1e-9:
            raise ValueError("Planner changed the explicitly requested time window")
    return {"engineering_functions": functions, "history_window_minutes": float(minutes)}


def compare_series(temporals):
    """Compare endpoints on an identical simulation-time interval, without interpolation."""
    if len(temporals) != 2 or any(x.get("status") != "AVAILABLE" for x in temporals):
        raise ValueError("Both temporal series must be available")
    histories = [x["history"] for x in temporals]
    if any(h["truncated_by_limit"] for h in histories):
        raise ValueError("Truncated series cannot support a complete comparison")
    samples = [h["samples"] for h in histories]
    if any(len(s) < 2 for s in samples):
        raise ValueError("At least two samples per series required")
    # Use the common exact timestamps; do not silently interpolate or compare
    # different time windows. Rounded simulation seconds are the stored evidence basis.
    indexed = [{float(x["simulation_seconds"]): float(x["value"]) for x in s} for s in samples]
    if any(len(m) != len(s) for m, s in zip(indexed, samples)):
        raise ValueError("Duplicate simulation timestamps")
    shared = sorted(set(indexed[0]) & set(indexed[1]))
    if len(shared) < 2:
        raise ValueError("Insufficient common simulation timestamps")
    output = []
    for temporal, values in zip(temporals, indexed):
        aligned = [{"simulation_seconds": t, "value": values[t]} for t in shared]
        analytics = summarize_history(aligned)
        baseline = aligned[0]["value"]
        relative = None if baseline == 0 else 100 * analytics["endpoint_change"] / abs(baseline)
        output.append({"signal": temporal["signal"], "sample_count_aligned": len(shared),
                       "first_value": baseline, "last_value": aligned[-1]["value"],
                       "endpoint_change": analytics["endpoint_change"],
                       "relative_endpoint_change_percent": relative,
                       "slope_per_simulation_minute": analytics["linear_regression_slope_per_simulation_minute"]})
    comparable = all(x["relative_endpoint_change_percent"] is not None for x in output)
    winner = None
    if comparable:
        magnitudes = [abs(x["relative_endpoint_change_percent"]) for x in output]
        winner = "equal" if math.isclose(*magnitudes, rel_tol=1e-9, abs_tol=1e-12) else (0 if magnitudes[0] > magnitudes[1] else 1)
    return {"alignment": "exact_common_simulation_timestamps_no_interpolation",
            "common_start_simulation_seconds": shared[0],
            "common_end_simulation_seconds": shared[-1],
            "common_sample_count": len(shared), "series": output,
            "larger_absolute_relative_change_index": winner,
            "comparison_available": comparable}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    parser.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    parser.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--history-limit", type=int, default=1000)
    parser.add_argument("--answer-format", choices=("freeform", "structured"), default="freeform")
    parser.add_argument("--output", default="reports/tep_nexus_two_function_comparison.json")
    args = parser.parse_args()
    if args.history_limit < 2:
        parser.error("--history-limit must be at least 2")
    if not os.getenv("TEP_TIMESCALE_DSN"):
        parser.error("TEP_TIMESCALE_DSN is not set")
    report = {"schema_version": 1, "generated_at_utc": utc_now(), "question": args.question,
              "status": "STARTED", "validated_plan": None, "evidence": None,
              "llm_answer": None, "llm_answer_validation": "NOT_RUN",
              "llm_answer_validation_details": None}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        registry = load_supported_functions(args.mapping_discovery, args.temporal_coverage, args.run_id)
        system = ('Return only a JSON object with exactly engineering_functions '
                  '(array of two explicit identifiers from the allowed list) and '
                  'history_window_minutes (number, default 10). Never invent an identifier. '
                  'Convert explicit hours to minutes. Allowed: ' + ", ".join(sorted(registry)))
        raw = ollama_chat(args.ollama_url, args.model, system, args.question)
        report["raw_plan"] = raw
        plan = validate_comparison_plan(raw, args.question, registry)
        report["validated_plan"] = plan
        mappings = [resolve_supported_mapping(args.graphdb_url, f, registry)
                    for f in plan["engineering_functions"]]
        temporals = [retrieve_temporal_context(os.environ["TEP_TIMESCALE_DSN"], args.run_id,
                     m["operational_signal"], plan["history_window_minutes"], args.history_limit)
                     for m in mappings]
        result = compare_series(temporals)
        for item, function in zip(result["series"], plan["engineering_functions"]):
            item["engineering_function"] = function
        evidence = {"mappings": mappings, "comparison": result, "run_id": args.run_id,
                    "run_identity_source": "operator_supplied",
                    "engineering_mapping": "PROVISIONAL",
                    "physical_sensor_binding": "NOT_VERIFIED",
                    "shared_run_provenance": "NOT_VERIFIED",
                    "causal_inference": "NOT_SUPPORTED"}
        report["evidence"] = evidence
        report["answer_format"] = args.answer_format
        answer_system = (structured_prompt() if args.answer_format == "structured" else
            'Return JSON with answer (string) and limitations (array of strings). '
            'Use ONLY provided evidence. State the compared simulation-time interval, '
            'endpoint changes, and relative changes where available. '
            'Do not infer causation or physical sensor verification. '
            'Distinguish provisional mapping from verified evidence.')
        report["llm_answer"] = ollama_chat(args.ollama_url, args.model,
            answer_system,
            json.dumps({"question": args.question, "evidence": evidence}))
        validation = (validate_structured_answer(report["llm_answer"], evidence)
                      if args.answer_format == "structured" else
                      validate_comparison_answer(report["llm_answer"], evidence))
        report["llm_answer_validation_details"] = validation
        report["llm_answer_validation"] = validation["status"]
        report["status"] = ("COMPLETED" if validation["status"] == "CHECKS_PASSED_LIMITED_SCOPE"
                            else "COMPLETED_WITH_ANSWER_CHECK_FAILURES")
    except Exception as exc:
        report["status"] = "ERROR"
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(report["error"], file=sys.stderr)
    finally:
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("Saved:", output)
    if report["status"] == "ERROR":
        sys.exit(1)


if __name__ == "__main__":
    main()
