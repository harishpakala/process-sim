"""Live four-domain semantic integration matrix; no SPARQL compilation.

Run: python -m process_sim.dtwise.experimental_shacl_three_domain_integration
Optional: --case asset-only --debug
Requires local Ollama for real Qwen selection.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from process_sim.dtwise.experimental_shacl_cross_domain_mappings import load_cross_domain_mappings
from process_sim.dtwise.experimental_shacl_n_domain_live import prepare_live_candidates
from process_sim.dtwise.experimental_shacl_n_domain_selection import SYSTEM_PROMPT, validate_n_domain_selection
from process_sim.dtwise.experimental_shacl_ollama import ollama_select

DOMAINS = ("dexpi", "ecad", "assetinventory", "opcuaconnectivity")

# Name, question, requested output owner labels by domain.
# Join participants are intentionally separate from output projection.
CASES = (
    ("all-four", "Show DEXPI Equipment, ECAD Device, AssetInventory Asset, and OPCUAConnectivity SignalMapping corresponding by AssetIdentifier.",
     {"dexpi": "Equipment", "ecad": "Device", "assetinventory": "Asset", "opcuaconnectivity": "SignalMapping"}),
    ("all-four-reordered", "Using AssetIdentifier, show OPCUAConnectivity SignalMapping, AssetInventory Asset, ECAD Device, and DEXPI Equipment.",
     {"dexpi": "Equipment", "ecad": "Device", "assetinventory": "Asset", "opcuaconnectivity": "SignalMapping"}),
    ("opcua-only", "Return only OPCUAConnectivity SignalMapping records whose AssetIdentifier matches DEXPI Equipment, ECAD Device, and AssetInventory Asset. Use the other three entities for matching, not as outputs.",
     {"opcuaconnectivity": "SignalMapping"}),
    ("asset-only-four", "Return only AssetInventory Asset records whose AssetIdentifier matches DEXPI Equipment, ECAD Device, and OPCUAConnectivity SignalMapping. Use the other three entities for matching, not as outputs.",
     {"assetinventory": "Asset"}),
    ("device-only-four", "Return only ECAD Device records whose AssetIdentifier matches DEXPI Equipment, AssetInventory Asset, and OPCUAConnectivity SignalMapping. Use the other three entities for matching, not as outputs.",
     {"ecad": "Device"}),
    ("equipment-only-four", "Return only DEXPI Equipment records whose AssetIdentifier matches ECAD Device, AssetInventory Asset, and OPCUAConnectivity SignalMapping. Use the other three entities for matching, not as outputs.",
     {"dexpi": "Equipment"}),
)


# This matrix explicitly names these three SHACL owner labels in every question.
EXPECTED_OWNERS = {"dexpi": "Equipment", "ecad": "Device", "assetinventory": "Asset", "opcuaconnectivity": "SignalMapping"}


def _owner(candidate: dict) -> str:
    return candidate["path"].split(" → ")[0].strip()


def check_semantics(selection: dict, prompt: dict, outputs: dict[str, str]) -> tuple[bool, str]:
    if selection["status"] != "selected":
        return False, "Expected selected status"
    paths = {p["id"]: p for p in prompt["identifier_path_candidates"]}
    results = {p["id"]: p for p in prompt["result_candidates"]}
    edges = {e["id"]: e for e in prompt["mapping_candidates"]}
    selected_paths = [paths[cid] for cid in selection["identifier_path_ids"]]
    selected_results = [results[cid] for cid in selection["result_ids"]]
    selected_edges = [edges[cid] for cid in selection["mapping_ids"]]

    # Exactly one identifier owner per named domain, irrespective of projection.
    if len(selected_paths) != len(DOMAINS):
        return False, "Expected one identifier path per domain"
    for domain, owner in EXPECTED_OWNERS.items():
        matching = [p for p in selected_paths if p["domain"] == domain]
        if len(matching) != 1 or _owner(matching[0]).casefold() != owner.casefold():
            return False, f"Incorrect identifier owner in {domain}"
        if matching[0]["path"].split(" → ")[-1].strip().casefold() != "assetidentifier":
            return False, f"Incorrect identifier property in {domain}"

    # Projection must match what the question requests, not every join participant.
    if len(selected_results) != len(outputs):
        return False, "Incorrect number of output results"
    for domain, owner in outputs.items():
        matching = [r for r in selected_results if r["domain"] == domain]
        if len(matching) != 1 or matching[0]["kind"] != "result":
            return False, f"Missing entity result for {domain}"
        if _owner(matching[0]).casefold() != owner.casefold():
            return False, f"Incorrect result owner in {domain}"

    # Selected mapping endpoints must match the chosen qualified identifier paths.
    chosen = {p["id"] for p in selected_paths}
    adjacency = {d: set() for d in DOMAINS}
    for edge in selected_edges:
        left, right = edge["left_domain"], edge["right_domain"]
        if left not in adjacency or right not in adjacency:
            return False, "Unexpected mapping domain"
        if not any(a["left_id"] in chosen and a["right_id"] in chosen
                   for a in edge["join_alternatives"]):
            return False, "Mapping does not join selected owner paths"
        adjacency[left].add(right)
        adjacency[right].add(left)
    visited = set()
    frontier = [DOMAINS[0]]
    while frontier:
        domain = frontier.pop()
        if domain not in visited:
            visited.add(domain)
            frontier.extend(adjacency[domain] - visited)
    if visited != set(DOMAINS):
        return False, "Mapping graph does not connect all four domains"
    return True, "Semantic assertions passed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live Qwen four-domain integration matrix")
    parser.add_argument("--case", choices=[case[0] for case in CASES])
    parser.add_argument("--debug", action="store_true", help="Show offered candidates and failure details")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[3]
    schema = json.loads((root / "semantic/ontology2/dtwise/dtwise-schema-index.json").read_text(encoding="utf-8"))
    mappings = load_cross_domain_mappings(root / "semantic/ontology2/dtwise/cross-domain-mappings.json")
    cases = [case for case in CASES if args.case is None or case[0] == args.case]
    failures = 0
    total_start = perf_counter()
    for name, question, outputs in cases:
        start = perf_counter()
        raw = None
        try:
            prepared = prepare_live_candidates(schema, mappings, question, DOMAINS)
            prompt = prepared["prompt"]
            if args.debug:
                print("QUESTION:", question)
                print("OFFERED:", json.dumps(prompt, ensure_ascii=False, indent=2))
            if not prompt["mapping_candidates"]:
                raise ValueError("No SHACL-qualified approved mapping candidates")
            raw = ollama_select(prompt, system_prompt=SYSTEM_PROMPT)
            selection = validate_n_domain_selection(raw, prepared)
            passed, detail = check_semantics(selection, prompt, outputs)
        except Exception as exc:
            passed, detail = False, f"{type(exc).__name__}: {exc}"
        failures += not passed
        print(f"{name}: {'PASS' if passed else 'FAIL'} {perf_counter() - start:.2f}s")
        print("QWEN:", raw if raw is not None else "(no response)")
        if not passed or args.debug:
            print("DETAIL:", detail)
    print(f"TOTAL: {'PASS' if not failures else 'FAIL'} "
          f"{len(cases) - failures}/{len(cases)} {perf_counter() - total_start:.2f}s")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
