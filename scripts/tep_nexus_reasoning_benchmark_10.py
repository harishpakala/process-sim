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
    ("semantic_lookup", "According to GraphDB AAS, which operational signals map to FI_101 and PI_101? State each mapping's status and source."),
    ("temporal_retrieval", "For the specified run, report the first and last values of XMEAS1 and XMEAS7 in the last 10 simulation minutes and the actual interval."),
    ("semantic_temporal_join", "Using the GraphDB mappings and TimescaleDB observations, report signed relative endpoint percentage changes for FI_101 and PI_101. Explain the joins and their status."),
    ("comparison_semantics", "Give BOTH (a) the greater signed relative endpoint change and (b) the greater absolute relative endpoint change for FI_101 versus PI_101, with numerical justification. Distinguish signed ordering from magnitude."),
    ("time_alignment", "Were FI_101 and PI_101 compared at exactly matching simulation timestamps? State alignment, shared sample count, interval, and interpolation status."),
    ("semantic_relationship", "Which relationships between FI_101 and PI_101 are actually established by the available AAS mapping evidence? Can one function be said to influence the other? Separate facts from hypotheses."),
    ("provenance_claim", "Evaluate the claim that FI_101 and PI_101 are verified physical sensors belonging to the same physical run. Distinguish operator-supplied run ID from independently verified provenance."),
    ("cross_source_corroboration", "Do GraphDB mappings plus TimescaleDB values establish verified physical changes in FI_101 and PI_101? Separate observed signal trends, provisional attribution, and independent corroboration."),
    ("hypothesis_evaluation", "Assess independent signal variation, causal influence, and incorrect or provisional signal attribution as competing hypotheses. Identify what is supported, unresolved, and what evidence would discriminate them."),
    ("integrated_assessment", "Provide an evidence-grounded assessment of FI_101 and PI_101 over the last 10 simulation minutes. Integrate mapping, alignment, signed and absolute changes, provenance and causality. List supported conclusions and missing verification evidence."),
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
    report = {"schema_version": 1, "generated_at_utc": utc_now(),
              "benchmark": "TEP_NEXUS_10_LEVEL_V1", "model": args.model,
              "run_id": args.run_id, "status": "STARTED", "results": [],
              "evaluation_scope": "format checks only; factual and semantic grading pending"}
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
    parser.add_argument("--output", default="reports/tep_nexus_reasoning_benchmark_10.json")
    args = parser.parse_args()
    report = run(args)
    print("Saved:", args.output, "status:", report["status"])
    if report["status"] == "ERROR":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
