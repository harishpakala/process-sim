"""Read-only benchmark report registry for the experimental Web UI.

Never executes evaluation scripts or accepts filesystem paths from clients.
Only exposes existing local JSON reports, with provenance and coverage labels.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]
REPORTS = (
    ("33", "Without Run ID", "Exploratory single-predicate SPARQL", "experiments/vector_graph_rag/data/simple_llm_sparql_33_results.json"),
    ("36D", "Without Run ID", "Frozen ontology path selection", "experiments/vector_graph_rag/data/multihop_nl_36_results.json"),
    ("37", "Without Run ID", "Curated path benchmark (not held-out)", "experiments/vector_graph_rag/data/path_benchmark_37_results.json"),
    ("39", "Without Run ID", "Frozen retrieval comparison; diagnostic labels may not be independent", "experiments/vector_graph_rag/data/frozen_comparison_39_results.json"),
    ("40", "With Run ID", "Function selection and live mapping diagnostic", "reports/vtkg_function_selection_diagnostic.json"),
    ("41", "With Run ID", "Temporal plan validation and read-only AVG diagnostic", "reports/vtkg_end_to_end_41.json"),
)

def list_reports():
    items = []
    for identifier, mode, description, relative in REPORTS:
        path = ROOT / relative
        item = {"id": identifier, "mode": mode, "description": description,
                "reportPath": relative, "available": False}
        if path.is_file():
            try:
                if path.stat().st_size > 2_000_000:
                    raise ValueError("Report exceeds 2 MB display limit")
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(data, dict):
                    raise ValueError("Report root must be an object")
                item["available"] = True
                item["report"] = data
            except (OSError, ValueError) as exc:
                item["error"] = str(exc)
        items.append(item)
    return {"kind": "local_experiment_reports", "execution": "none",
            "warning": "Reports are local artifacts, not live runs or independently verified accuracy scores.",
            "benchmarks": items}


def list_questions():
    """Source-backed question inventory; no generated scores or execution."""
    from process_sim.api.paper_query import questions as paper_questions
    groups = []
    paper = paper_questions()
    groups.append({"id": "PAPER", "title": "TEP NEXUS paper Q1–Q12",
                   "provenance": "Existing paper question registry; not Experiment 36D.",
                   "questions": [{"id": q["id"], "question": q["question"],
                                  "mode": "With Run ID" if q["requiresRun"] else "Without Run ID",
                                  "expected": "Evidence-grounded answer or justified abstention",
                                  "note": "Requires live evaluation for a correctness decision"}
                                 for q in paper]})
    diagnostic = json.loads((ROOT / "experiments/vector_graph_rag/data/two_aggregation_diagnostics_39.json").read_text(encoding="utf-8-sig"))
    groups.append({"id": "39", "title": "Experiment 39 targeted aggregation diagnostics",
                   "provenance": diagnostic.get("annotation_provenance"),
                   "questions": [{"id": c["id"], "question": c["question"],
                                  "mode": "With Run ID" if c["id"] == "VTKG_DIAG_01" else "Without Run ID",
                                  "expected": c["expected_path_id"],
                                  "note": c["annotation_note"]} for c in diagnostic["cases"]]})
    # Experiment 37 generates its cases from the current SHACL path catalog.
    # Only list exact cases from a locally produced report; do not invent questions.
    path = ROOT / "experiments/vector_graph_rag/data/ontology_path_benchmark_37_results.json"
    if path.is_file() and path.stat().st_size <= 2_000_000:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
        cases = report.get("cases", [])
        groups.append({"id": "37", "title": "Experiment 37 catalog-derived path cases",
                       "provenance": report.get("dataset_type", "Catalog-derived development cases"),
                       "questions": [{"id": c["id"], "question": c["question"],
                                      "mode": "Without Run ID", "expected": c.get("expected_path_id"),
                                      "note": c.get("source", "")} for c in cases if isinstance(c, dict) and c.get("question")]})
    else:
        groups.append({"id": "37", "title": "Experiment 37 catalog-derived path cases",
                       "provenance": "Generate from the local SHACL catalog using Experiment 37.",
                       "questions": [], "note": "Run Experiment 37 to populate the exact generated questions."})
    return {"kind": "source_backed_benchmark_questions", "groups": groups,
            "warning": "Question coverage does not imply held-out evaluation or a passing score."}
