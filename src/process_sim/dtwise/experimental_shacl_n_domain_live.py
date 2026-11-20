"""Run one real N-domain Qwen selection against the checked-in SHACL index.

Usage (repository root):
    python -m process_sim.dtwise.experimental_shacl_n_domain_live

This is a diagnostic, not a semantic PASS assertion. It does not compile or
execute SPARQL, infer mapping IDs, or alter the single-domain planner.
"""
from __future__ import annotations

import json
from pathlib import Path

from process_sim.dtwise.experimental_shacl_candidates import prepare_candidates
from process_sim.dtwise.experimental_shacl_cross_domain_mappings import load_cross_domain_mappings
from process_sim.dtwise.experimental_shacl_n_domain_selection import (
    prepare_n_domain_selection, validate_n_domain_selection, SYSTEM_PROMPT,
)
from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.experimental_shacl_subgraph import SubgraphIndex


def prepare_live_candidates(schema: dict, mappings: dict[str, dict],
                            question: str, domains: tuple[str, ...]) -> dict:
    """Include every owner of mapped identifier predicates in supplied domains.

    No domain-pair-specific owner choice, keyword routing or candidate ranking.
    All literal properties of included owners are offered as result candidates.
    """
    qualified = {}
    for domain in domains:
        index = SubgraphIndex.from_schema_index(schema, domain)
        mapped_predicates = {
            m[side + "_property"]
            for m in mappings.values() if m.get("verified") is True
            for side in ("left", "right") if m[side + "_domain"] == domain
        }
        owners = sorted({
            owner for owner, properties in index.properties.items()
            if any(p["predicate"] in mapped_predicates for p in properties)
        })
        if not owners:
            raise SelectionContractError(f"No mapped SHACL identifier owner in {domain}")
        extracted = index.extract(owners)
        extracted["question"] = question
        prepared = prepare_candidates(extracted)
        qualified[domain] = qualify_candidates(index, prepared)
    return prepare_n_domain_selection(question, qualified, mappings)


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    schema_path = root / "semantic/ontology2/dtwise/dtwise-schema-index.json"
    mapping_path = root / "semantic/ontology2/dtwise/cross-domain-mappings.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    mappings = load_cross_domain_mappings(mapping_path)
    question = "Show DEXPI Equipment and its corresponding ECAD entity using AssetIdentifier"
    prepared = prepare_live_candidates(schema, mappings, question, ("dexpi", "ecad"))
    print("=== ACTUAL QUALIFIED QWEN INPUT ===")
    print(json.dumps(prepared["prompt"], indent=2, ensure_ascii=False))
    if not prepared["prompt"]["mapping_candidates"]:
        print("ABSTAIN: No qualified approved cross-domain mapping")
        return 2
    print("=== LIVE QWEN SELECTION ===")
    try:
        raw = ollama_select(prepared["prompt"], system_prompt=SYSTEM_PROMPT)
        print("RAW MODEL RESPONSE:", raw)
        selection = validate_n_domain_selection(raw, prepared)
    except (SelectionContractError, RuntimeError) as exc:
        print(f"VALIDATION/TRANSPORT FAILURE: {exc}")
        return 2
    print(json.dumps(selection, indent=2, ensure_ascii=False))
    print("=== INTERPRETATION ===")
    print("Contract and owner/result topology validated; semantic intent is NOT independently verified.")
    print("No SPARQL generated or executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
