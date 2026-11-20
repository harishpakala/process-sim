"""Probe structural Phase 4 JOIN + two AND/OR filters on existing 1D cases.

Offline identification only: no Ollama, embeddings, SHACL qualification,
SPARQL compilation, or production routing changes.

From the repository root:
    python tests/experimental/probe_complex_query_identification.py
"""
from pathlib import Path
import runpy

from process_sim.dtwise.shacl_planner.query_classifier import (
    classify_single_domain_query,
    extract_query_structure,
)

# Load the existing integration cases by file path. The tests directory is
# not necessarily importable as a package in a direct script invocation.
CASES = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "integration" / "run_shacl_planner.py")
)["CASES"]


def identify_type6(question):
    """Recognize JOIN + exactly two equality filters with AND/OR syntax.

    This is a syntactic probe, not proof of a SHACL-valid join. In particular,
    the actual owner and property paths are verified later by the planner.
    """
    structure = extract_query_structure(question)
    if not structure or structure.get("unsupported"):
        return None
    filters = structure["filters"]
    logic = structure["boolean_operator"]
    if not structure["sibling"] or len(filters) != 2 or logic not in ("AND", "OR"):
        return None
    return {
        "requires_join": True,
        "filter_count": len(filters),
        "boolean_operator": logic,
        "filters": [
            {"property": property_name, "value": value}
            for property_name, value in filters
        ],
    }


def main():
    matched = 0
    print("1D Phase 4 JOIN + two AND/OR filters: structural probe (offline)\n")
    for test in CASES:
        name, question = test["name"], test["question"]
        identified = identify_type6(question)
        routing = classify_single_domain_query(question)
        matched += identified is not None
        print(f"{name}: {'MATCH' if identified is not None else 'None'}")
        print(f"  existing operation: {routing['operation']}")
        print(f"  Type 6 identification: {identified}")
    print(f"\nTOTAL: {matched} non-null / {len(CASES) - matched} None / {len(CASES)} 1D queries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
