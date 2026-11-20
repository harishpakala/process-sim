"""Live DEXPI/ECAD integration matrix: terse PASS/FAIL and elapsed time.

Run: python -m process_sim.dtwise.experimental_shacl_two_domain_integration
Requires local Ollama for cases with qualified mapping candidates.
No SPARQL compilation or RDF instance verification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from process_sim.dtwise.experimental_shacl_cross_domain_mappings import load_cross_domain_mappings
from process_sim.dtwise.experimental_shacl_n_domain_live import prepare_live_candidates
from process_sim.dtwise.experimental_shacl_n_domain_selection import (
    SYSTEM_PROMPT, validate_n_domain_selection,
)
from process_sim.dtwise.experimental_shacl_ollama import ollama_select


# Name, question, expected status, expected owner labels by domain (if selected).
# Entity and identifier IDs are discovered dynamically from SHACL, not hardcoded.
CASES = (
    ("equipment-device", "Find DEXPI Equipment and its corresponding ECAD Device using AssetIdentifier.",
     "selected", {"dexpi": "Equipment", "ecad": "Device"}),
    ("device-equipment-reversed", "Return only ECAD Device records whose AssetIdentifier matches DEXPI Equipment. Use DEXPI Equipment for matching, not as an output.",
     "selected", {"dexpi": "Equipment", "ecad": "Device"}, {"ecad"}),
    ("equipment-device-join", "Match DEXPI Equipment with ECAD Device by AssetIdentifier.",
     "selected", {"dexpi": "Equipment", "ecad": "Device"}),
    ("equipment-symbol", "Find DEXPI Equipment and the corresponding ECAD Symbol using AssetIdentifier.",
     "selected", {"dexpi": "Equipment", "ecad": "Symbol"}),
    ("actuating-device", "Match DEXPI ActuatingFunction to ECAD Device using AssetIdentifier.",
     "selected", {"dexpi": "ActuatingFunction", "ecad": "Device"}),
    ("instrumentation-symbol", "Find DEXPI InstrumentationFunction and ECAD Symbol sharing AssetIdentifier.",
     "selected", {"dexpi": "InstrumentationFunction", "ecad": "Symbol"}),
    ("unspecified-owners", "Find corresponding DEXPI and ECAD entities using AssetIdentifier, without specifying which entity kinds.",
     "ambiguous", None),
    ("unsupported-identifier", "Match DEXPI Equipment to ECAD Device using ProductIdentifier only; do not use AssetIdentifier.",
     "unresolved", None),
)


def _check_selected(selection: dict, prompt: dict, owners: dict[str, str],
                    output_domains: set[str] | None = None) -> bool:
    if selection["status"] != "selected":
        return False
    paths = {p["id"]: p for p in prompt["identifier_path_candidates"]}
    results = {p["id"]: p for p in prompt["result_candidates"]}
    edges = {e["id"]: e for e in prompt["mapping_candidates"]}
    if len(selection["mapping_ids"]) != 1 or len(selection["identifier_path_ids"]) != 2:
        return False
    if len(selection["result_ids"]) != len(output_domains or owners):
        return False
    selected_edge = edges[selection["mapping_ids"][0]]
    if {selected_edge["left_domain"], selected_edge["right_domain"]} != set(owners):
        return False
    selected_paths = [paths[cid] for cid in selection["identifier_path_ids"]]
    selected_results = [results[cid] for cid in selection["result_ids"]]
    for domain, owner in owners.items():
        domain_paths = [p for p in selected_paths if p["domain"] == domain]
        domain_results = [r for r in selected_results if r["domain"] == domain]
        if len(domain_paths) != 1 or len(domain_results) != (1 if domain in (output_domains or owners) else 0):
            return False
        if domain_paths[0]["path"].split(" → ")[0].casefold() != owner.casefold():
            return False
        if domain_paths[0]["path"].split(" → ")[-1].casefold() != "assetidentifier":
            return False
        if domain_results and domain_results[0]["path"].split(" → ")[0].casefold() != owner.casefold():
            return False
    return True


def run_case(schema: dict, mappings: dict, case: tuple, *, debug: bool = False) -> bool:
    _, question, expected, owners, *output_spec = case
    prepared = prepare_live_candidates(schema, mappings, question, ("dexpi", "ecad"))
    prompt = prepared["prompt"]
    if debug:
        print('QUESTION:', question)
        print('OFFERED:', json.dumps(prompt, indent=2, ensure_ascii=False))
    if prompt["mapping_candidates"]:
        raw = ollama_select(prompt, system_prompt=SYSTEM_PROMPT)
        if debug:
            print('RAW QWEN:', raw)
        selection = validate_n_domain_selection(raw, prepared)
    else:
        # No approved qualified mapping is a deterministic unresolved outcome.
        selection = {"status": "unresolved", "result_ids": [],
                     "identifier_path_ids": [], "mapping_ids": []}
    if debug:
        print('VALIDATED:', json.dumps(selection, indent=2, ensure_ascii=False))
        print('EXPECTED:', expected, owners)
    if selection["status"] != expected:
        return False
    if expected != "selected":
        return not any(selection[key] for key in (
            "result_ids", "identifier_path_ids", "mapping_ids"
        ))
    return _check_selected(selection, prompt, owners, output_spec[0] if output_spec else None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live two-domain Qwen integration tests")
    parser.add_argument("--case", choices=[case[0] for case in CASES],
                        help="Run only one named case")
    parser.add_argument("--debug", action="store_true",
                        help="Print candidate payload, Qwen output and validation details")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    schema = json.loads(
        (root / "semantic/ontology2/dtwise/dtwise-schema-index.json").read_text(encoding="utf-8")
    )
    mappings = load_cross_domain_mappings(
        root / "semantic/ontology2/dtwise/cross-domain-mappings.json"
    )
    failures = 0
    total_start = perf_counter()
    selected_cases = [case for case in CASES if args.case is None or case[0] == args.case]
    for case in selected_cases:
        start = perf_counter()
        try:
            passed = run_case(schema, mappings, case, debug=args.debug)
        except Exception as exc:
            if args.debug:
                print('ERROR:', type(exc).__name__, str(exc))
            passed = False
        failures += not passed
        print(f"{case[0]}: {'PASS' if passed else 'FAIL'} {perf_counter() - start:.2f}s")
    print(f"TOTAL: {'PASS' if not failures else 'FAIL'} "
          f"{len(selected_cases) - failures}/{len(selected_cases)} {perf_counter() - total_start:.2f}s")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
