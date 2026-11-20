"""Live diagnostic scenarios: DEXPI, ECAD and AssetInventory only.

Run: python -m process_sim.dtwise.experimental_shacl_n_domain_scenarios
Qwen is called only when qualified mapping candidates exist. No SPARQL.
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
        ("dexpi", "ecad"),
    ),
    (
        "unsupported-identifier",
        "Match DEXPI Equipment to ECAD Device and AssetInventory entities using ProductIdentifier only; do not use AssetIdentifier.",
        {"unresolved"},
        DOMAINS,
    ),
    (
        "three-domain-asset",
        "Show DEXPI Equipment, its corresponding ECAD Device, and matching AssetInventory entity using AssetIdentifier.",
        {"selected"},
        DOMAINS,
    ),
)


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    schema = json.loads((root / "semantic/ontology2/dtwise/dtwise-schema-index.json").read_text(encoding="utf-8"))
    mappings = load_cross_domain_mappings(
        root / "semantic/ontology2/dtwise/cross-domain-mappings.json"
    )
    failures = 0
    for name, question, expected, domains in SCENARIOS:
        print(f"\n=== {name} ===")
        print("QUESTION:", question)
        try:
            prepared = prepare_live_candidates(schema, mappings, question, domains)
            prompt = prepared["prompt"]
            print("OFFERED:", json.dumps({
                "result_candidate_count": len(prompt["result_candidates"]),
                "identifier_paths": prompt["identifier_path_candidates"],
                "mapping_bridges": [
                    {
                        "id": edge["id"],
                        "bridge_role": edge.get("bridge_role"),
                        "left_domain": edge["left_domain"],
                        "right_domain": edge["right_domain"],
                        "left_property": edge["left_property"],
                        "right_property": edge["right_property"],
                        "left_identifier_candidate_ids": edge["left_identifier_candidate_ids"],
                        "right_identifier_candidate_ids": edge["right_identifier_candidate_ids"],
                        "join_alternatives": edge.get("join_alternatives", []),
                        "approved_owner_pair_candidate_ids": edge.get(
                            "approved_owner_pair_candidate_ids"
                        ),
                    }
                    for edge in prompt["mapping_candidates"]
                ],
            }, indent=2))
            if not prompt["mapping_candidates"]:
                print("NO QUALIFIED IDENTIFIER BRIDGES: deterministic unresolved; Qwen not called")
                selection = {"status": "unresolved", "result_ids": [],
                             "identifier_path_ids": [], "mapping_ids": [],
                             "reason": "No qualified identifier bridge candidates"}
            else:
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
