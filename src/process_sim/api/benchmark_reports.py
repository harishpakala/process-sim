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
