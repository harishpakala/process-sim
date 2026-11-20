"""Live diagnostic scenarios: DEXPI, ECAD and AssetInventory only.

Run: python -m process_sim.dtwise.experimental_shacl_n_domain_scenarios
Each scenario makes exactly one Qwen call. No SPARQL is generated/executed.
"""
from __future__ import annotations

import json
from pathlib import Path

from process_sim.dtwise.experimental_shacl_cross_domain_mappings import load_cross_domain_mappings
from process_sim.dtwise.experimental_shacl_n_domain_live import prepare_live_candidates
from process_sim.dtwise.experimental_shacl_n_domain_selection import (
    SYSTEM_PROMPT, validate_n_domain_selection,
)
from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


DOMAINS = ("dexpi", "ecad", "assetinventory")
SCENARIOS = (
    (
        "ambiguous-owner",
        "Find the corresponding DEXPI and ECAD entities using AssetIdentifier, without specifying which entity kinds.",
        {"ambiguous"},
    ),
    (
        "unsupported-identifier",
        "Match DEXPI Equipment to ECAD Device and AssetInventory entities using ProductIdentifier only; do not use AssetIdentifier.",
        {"unresolved"},
    ),
    (
        "three-domain-asset",
        "Show DEXPI Equipment, its corresponding ECAD Device, and matching AssetInventory entity using AssetIdentifier.",
        {"selected"},
    ),
)


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    schema = json.loads((root / "semantic/ontology2/dtwise/dtwise-schema-index.json").read_text(encoding="utf-8"))
    mappings = load_cross_domain_mappings(
        root / "semantic/ontology2/dtwise/cross-domain-mappings.json"
    )
    failures = 0
    for name, question, expected in SCENARIOS:
        print(f"\n=== {name} ===")
        print("QUESTION:", question)
        try:
            prepared = prepare_live_candidates(schema, mappings, question, DOMAINS)
            prompt = prepared["prompt"]
            print("OFFERED:", json.dumps({
                "results": len(prompt["result_candidates"]),
                "identifiers": len(prompt["identifier_path_candidates"]),
                "mappings": [m["id"] for m in prompt["mapping_candidates"]],
            }, indent=2))
            raw = ollama_select(prompt, system_prompt=SYSTEM_PROMPT)
            print("RAW QWEN:", raw)
            selection = validate_n_domain_selection(raw, prepared)
            print("VALIDATED:", json.dumps(selection, indent=2))
            if selection["status"] not in expected:
                failures += 1
                print("STATUS MISMATCH: expected", sorted(expected))
            else:
                print("STATUS MATCH: review owner choices and reason manually")
        except (SelectionContractError, RuntimeError, ValueError) as exc:
            failures += 1
            print("VALIDATION/TRANSPORT FAILURE:", type(exc).__name__, str(exc))
    print("\nStructural validation does not establish semantic correctness or instance-level equality.")
    print("No SPARQL generated or executed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
