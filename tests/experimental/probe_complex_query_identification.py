"""Probe Phase 4 two-filter JOIN identification on the existing 1D cases.

No Ollama, embeddings, SHACL candidate qualification, or SPARQL compilation.

From the repository root:
    python tests/experimental/probe_complex_query_identification.py
"""
from process_sim.dtwise.shacl_planner.operations.phase4_and_join import (
    ALTERNATE_QUESTION,
    OR_QUESTION,
    QUESTION,
    _literals,
)
from process_sim.dtwise.shacl_planner.query_classifier import (
    classify_single_domain_query,
)
from tests.integration.run_shacl_planner import CASES


def identify_type6(question):
    """Run the actual Phase 4 two-filter question gate, without planning."""
    literals = _literals(question)
    if literals is None:
        return None
    if OR_QUESTION.fullmatch(question.strip()):
        logic = "OR"
    elif QUESTION.fullmatch(question.strip()):
        logic = "AND"
    elif ALTERNATE_QUESTION.fullmatch(question.strip()):
        logic = "AND"
    else:
        return None
    return {
        "join_owner": "Device",
        "filter_count": 2,
        "boolean_operator": logic,
        "filter_values": literals,
    }


def main():
    matched = 0
    print("1D Type 6 identification probe (no Ollama or SPARQL)\n")
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
