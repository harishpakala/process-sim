"""Offline structural flags for the existing 10 single-domain queries.

No Ollama, embeddings, SHACL qualification, or SPARQL compilation.
Run: python tests/experimental/probe_complex_query_identification.py
"""
from pathlib import Path
import runpy

from process_sim.dtwise.shacl_planner.query_classifier import (
    classify_single_domain_query,
    extract_query_structure,
)

CASES = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "integration" / "run_shacl_planner.py")
)["CASES"]


def identify_query_flags(question):
    """Return independent syntactic flags, not a SHACL-validated plan.

    None indicates an unrecognized or unsupported structure; boolean operators
    are counted only in the filter clause, not in result-property conjunctions.
    """
    structure = extract_query_structure(question)
    if structure is None or structure.get("unsupported"):
        return None
    filters = structure["filters"]
    operator = structure["boolean_operator"]
    return {
        "join": bool(structure["sibling"]),
        "boolean": operator in ("AND", "OR", "MIXED"),
        "filter": bool(filters),
        "boolean_operator": operator,
        "filter_count": len(filters),
    }


def main():
    print("1D query identification flags (offline; no Ollama)\n")
    for test in CASES:
        flags = identify_query_flags(test["question"])
        routing = classify_single_domain_query(test["question"])
        if flags is None:
            print(f"{test['name']:<25} UNRECOGNIZED  operation={routing['operation']}")
            continue
        yn = lambda value: "YES" if value else "NO"
        print(
            f"{test['name']:<25} JOIN={yn(flags['join']):<3} "
            f"BOOLEAN={yn(flags['boolean']):<3} "
            f"FILTER={yn(flags['filter']):<3} "
            f"operator={flags['boolean_operator'] or '-':<5} "
            f"filters={flags['filter_count']} "
            f"operation={routing['operation']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
