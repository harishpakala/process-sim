"""Ten-question, read-only TEP NEXUS evidence-integration diagnostic.

All questions use one independently retrieved evidence snapshot. No synthetic
relationships, causal links, or physical provenance are introduced. Raw LLM
answers are preserved; automatic checks have explicitly limited scope.
"""
import argparse
import json
import os
from pathlib import Path

from tep_nexus_function_registry import load_supported_functions, resolve_supported_mapping
from tep_nexus_ollama_query_planner import ollama_chat, utc_now
from tep_nexus_semantic_temporal_live import retrieve_temporal_context
from tep_nexus_two_function_reasoning import compare_series

QUESTIONS = [
    ("semantic_lookup", "From the supplied mappings array ONLY, return for FI_101 and PI_101: engineering_function, operational_signal, mapping_status, and mapping_source. Do not interpret PROVISIONAL_ENGINEERING_MATCH as verified physical binding."),
    ("temporal_retrieval", "From comparison.series ONLY, report for XMEAS1 and XMEAS7 their first_value and last_value, and report comparison.common_start_simulation_seconds and common_end_simulation_seconds. These are aligned comparison endpoints, not necessarily raw-series endpoints."),
    ("semantic_temporal_join", "Join each supplied mapping to comparison.series using mapping.operational_signal == series.signal. Report engineering function, signal, relative_endpoint_change_percent including its sign, and mapping_status. State whether the mapping is verified or provisional."),
    ("comparison_semantics", "Use the two supplied relative_endpoint_change_percent numbers. Task A: compare the SIGNED numbers using >; report the function with the numerically greater value. Task B: compute abs(number) for each and compare those NONNEGATIVE magnitudes using >; report the function with the larger magnitude. State both percentages and both winners. Do not interchange Tasks A and B."),
    ("time_alignment", "Evaluate ONLY the alignment actually used in comparison, not the original raw-series timestamp sets. Read comparison.alignment, common_sample_count, common_start_simulation_seconds and common_end_simulation_seconds. Did the comparison use the SAME common timestamps for both series? Was interpolation used? State whether the evidence establishes that the original raw series had identical timestamp sets."),
    ("semantic_relationship", "List the function-to-signal links explicitly present in mappings. Separately answer: (1) Is a direct process-topology edge between FI_101 and PI_101 supplied? (2) Is causal influence established? If not supplied, say NOT ESTABLISHED FROM PROVIDED EVIDENCE rather than claiming it does not exist."),
    ("provenance_claim", "Classify each claim separately as VERIFIED, NOT_VERIFIED, or CONTRADICTED by the supplied evidence: (1) function-to-signal mapping is provisional; (2) physical sensor binding is verified; (3) the run identifier was supplied by the operator; (4) the two signals have independently verified shared physical-run provenance. Explain that NOT_VERIFIED is not equivalent to CONTRADICTED."),
    ("cross_source_corroboration", "Give three separate conclusions: (1) observed direction of each signal's endpoint change from comparison.series.endpoint_change; (2) confidence status of attribution from mappings.mapping_status; (3) whether independent physical sensor verification is supplied. Do not infer verified physical-process behavior from provisional mappings."),
    ("hypothesis_evaluation", "Evaluate H1: signal variation is independent, H2: one signal causally influences the other, H3: one provisional function-to-signal attribution is incorrect. Use only the supplied summary and mapping/provenance flags. Classify EACH as ESTABLISHED, CONTRADICTED, or UNDETERMINED. A possible hypothesis is not ESTABLISHED; absence of causal evidence does not CONTRADICT causality. Identify one additional evidence type needed for each hypothesis. Do not infer similarity of full time-series trajectories from endpoints or slopes alone."),
    ("integrated_assessment", "Return a complete evidence-based assessment with ALL six labeled parts: (1) both function-to-signal mappings and their provisional status; (2) shared comparison interval, sample count, and interpolation status; (3) signed endpoint percentage changes for both functions; (4) greater signed winner AND greater absolute-magnitude winner, with definitions; (5) physical binding, shared-run provenance, and causality verification status; (6) at least two specific additional evidence items needed to verify physical-process attribution or causal interpretation. Do not claim that a numerical simulation observation verifies a physical sensor."),
]

def build_evidence(args):
    registry = load_supported_functions(args.mapping_discovery, args.temporal_coverage, args.run_id)
    names = ("FI_101", "PI_101")
    if any(name not in registry for name in names):
        raise ValueError("FI_101 and PI_101 must both be supported by registry")
    mappings = [resolve_supported_mapping(args.graphdb_url, name, registry) for name in names]
    temporal = [retrieve_temporal_context(os.environ["TEP_TIMESCALE_DSN"], args.run_id,
                mapping["operational_signal"], 10.0, args.history_limit) for mapping in mappings]
    comparison = compare_series(temporal)
    for row, name in zip(comparison["series"], names):
        row["engineering_function"] = name
    return {"mappings": mappings, "comparison": comparison, "run_id": args.run_id,
            "run_identity_source": "operator_supplied", "engineering_mapping": "PROVISIONAL",
            "physical_sensor_binding": "NOT_VERIFIED",
            "shared_run_provenance": "NOT_VERIFIED", "causal_inference": "NOT_SUPPORTED"}

def evidence_for_level(level, evidence):
    # Do not leak unrelated fields to lower levels; preserve exact provenance
    # and all evidence needed for higher-level judgments.
    if level == 1:
        return {"mappings": evidence["mappings"]}
    if level == 2:
        return {"run_id": evidence["run_id"], "comparison": evidence["comparison"]}
    if level in (3, 4, 5):
        return {"mappings": evidence["mappings"], "comparison": evidence["comparison"]}
    return evidence

def limited_checks(level, answer, evidence):
    """Diagnostic anchors only: NOT a semantic correctness or entailment score."""
    if not isinstance(answer, dict) or set(answer) != {"answer", "evidence_used", "limitations"}:
        return {"status": "SCHEMA_FAILED", "checks": {"schema": False},
                "scope": "diagnostic_only_not_semantic_entailment"}
    valid_types = (isinstance(answer["answer"], str) and
                   isinstance(answer["evidence_used"], list) and
                   isinstance(answer["limitations"], list))
    checks = {"schema": valid_types, "nonempty_answer": (isinstance(answer["answer"], str) and bool(answer["answer"].strip()))}
    if not valid_types:
        checks["nonempty_answer"] = False
    return {"status": "BASIC_FORMAT_PASSED" if all(checks.values()) else "BASIC_FORMAT_FAILED",
            "checks": checks, "scope": "format_only_no_factual_or_semantic_grading",
            "manual_review_required": True}

def run(args):
    if args.history_limit < 2:
        raise ValueError("history-limit must be >= 2")
    if not os.getenv("TEP_TIMESCALE_DSN"):
        raise ValueError("TEP_TIMESCALE_DSN is not set")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 2, "generated_at_utc": utc_now(),
              "benchmark": "TEP_NEXUS_10_LEVEL_V2", "model": args.model,
              "run_id": args.run_id, "status": "STARTED", "results": [],
              "evaluation_scope": "format checks only; factual and semantic grading pending",
              "question_specification": "explicit evidence scope, operators, epistemic categories and completeness requirements"}
    try:
        evidence = build_evidence(args)
        report["evidence"] = evidence
        for level, (capability, question) in enumerate(QUESTIONS, 1):
            item = {"level": level, "capability": capability, "question": question,
                    "status": "STARTED"}
            report["results"].append(item)
            try:
                context = evidence_for_level(level, evidence)
                item["evidence_provided"] = context
                answer = ollama_chat(args.ollama_url, args.model,
                    "You are a read-only engineering evidence analyst. Return ONLY JSON "
                    "with exactly three keys: answer (string), evidence_used (array of strings), "
                    "limitations (array of strings). Use only the supplied evidence. "
                    "Clearly distinguish numerical observations, provisional semantic mappings, "
                    "and unverified physical claims. Do not invent evidence or causal links. "
                    "When asked to compare signed changes, compare signed numbers; "
                    "when asked for absolute magnitude, compare absolute values.",
                    json.dumps({"question": question, "evidence": context}))
                item["raw_llm_answer"] = answer
                item["validation"] = limited_checks(level, answer, evidence)
                item["status"] = item["validation"]["status"]
            except Exception as exc:
                item["status"] = "ERROR"
                item["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                # Save after every question to preserve partial experimental results.
                output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["status"] = ("COMPLETED" if all(x["status"] != "ERROR" for x in report["results"])
                            else "COMPLETED_WITH_ERRORS")
    except Exception as exc:
        report["status"] = "ERROR"
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        report["summary"] = {"questions": len(QUESTIONS), "attempted": len(report["results"]),
            "basic_format_passed": sum(x["status"] == "BASIC_FORMAT_PASSED" for x in report["results"]),
            "errors": sum(x["status"] == "ERROR" for x in report["results"]),
            "factual_accuracy": "NOT_GRADED",
            "semantic_grounding": "NOT_GRADED"}
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--mapping-discovery", default="reports/tep_nexus_mapping_discovery.json")
    parser.add_argument("--temporal-coverage", default="reports/tep_nexus_temporal_coverage.json")
    parser.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--history-limit", type=int, default=1000)
    parser.add_argument("--output", default="reports/tep_nexus_reasoning_benchmark_10_v2.json")
    args = parser.parse_args()
    report = run(args)
    print("Saved:", args.output, "status:", report["status"])
    if report["status"] == "ERROR":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
