"""Run 1-/2-/3-/4-domain live Qwen semantic tests in one command.

SPARQL is emitted only when requested.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from process_sim.dtwise.experimental_shacl_candidates import prepare_candidates
from process_sim.dtwise.experimental_shacl_planner_state_machine import run_retrieve_state_machine
from process_sim.dtwise.experimental_shacl_subgraph import SubgraphIndex
from process_sim.dtwise.experimental_shacl_cross_domain_mappings import load_cross_domain_mappings
from process_sim.dtwise.experimental_shacl_n_domain_live import prepare_live_candidates
from process_sim.dtwise.experimental_shacl_n_domain_selection import (
    SYSTEM_PROMPT, COMPACT_SYSTEM_PROMPT, compact_n_domain_prompt,
    validate_n_domain_selection,
)
from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_n_domain_sparql import compile_n_domain_sparql
from process_sim.dtwise.experimental_shacl_two_domain_integration import CASES as TWO_CASES, _check_selected as check_two
from process_sim.dtwise.experimental_shacl_three_domain_integration import (
    CASES as THREE_CASES, DOMAINS as THREE_DOMAINS, check_semantics as check_three,
)

from process_sim.dtwise.experimental_shacl_four_domain_integration import (
    CASES as FOUR_CASES, DOMAINS as FOUR_DOMAINS, check_semantics as check_four,
)

ONE_CASES = (
    ("device-local-id", "Show Device LocalId in ECAD", "selected", "LocalId"),
    ("unsupported-count", "Count Device LocalId in ECAD", "unresolved", None),
)
ONE_DOMAINS = ("ecad",)
TWO_DOMAINS = ("dexpi", "ecad")


def _run_two(selection: dict, prompt: dict, case: tuple) -> tuple[bool, str]:
    _, _, expected, owners, *projection = case
    if selection["status"] != expected:
        return False, f"Expected status {expected}; got {selection['status']}"
    if expected != "selected":
        empty = not any(selection[key] for key in ("result_ids", "identifier_path_ids", "mapping_ids"))
        return empty, "Correct abstention" if empty else "Abstention must have empty IDs"
    passed = check_two(selection, prompt, owners, projection[0] if projection else None)
    return passed, "Semantic assertions passed" if passed else "Result projection or owner/identifier mapping mismatch"


def _run_three(selection: dict, prompt: dict, case: tuple) -> tuple[bool, str]:
    return check_three(selection, prompt, case[2])


def _run_four(selection: dict, prompt: dict, case: tuple) -> tuple[bool, str]:
    return check_four(selection, prompt, case[2])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live N-domain Qwen integration suite")
    parser.add_argument("--domains", type=int, choices=(1, 2, 3, 4),
                        help="Run only one domain count (default: all)")
    parser.add_argument("--case", help="Run one case by name")
    parser.add_argument("--debug", action="store_true", help="Print offered candidates and validated selection")
    parser.add_argument("--prompt-format", choices=("full", "compact"), default="full",
                        help="Qwen input representation (default: full)")
    parser.add_argument("--model", default="qwen2.5-coder:7b",
                        help="Ollama model for semantic selection (default: qwen2.5-coder:7b)")
    parser.add_argument("--emit-sparql", action="store_true",
                        help="Print deterministic SELECT for independently validated selected plans")
    args = parser.parse_args(argv)

    suites = [(1, ONE_DOMAINS, case, None) for case in ONE_CASES] + [
        (2, TWO_DOMAINS, case, _run_two) for case in TWO_CASES
    ] + [
        (3, THREE_DOMAINS, case, _run_three) for case in THREE_CASES
    ] + [
        (4, FOUR_DOMAINS, case, _run_four) for case in FOUR_CASES
    ]
    selected = [
        item for item in suites
        if (args.domains is None or args.domains == item[0])
        and (args.case is None or args.case == item[2][0])
    ]
    if args.case is not None and not selected:
        parser.error(f"Unknown case for selected domain count: {args.case}")

    if not selected:
        parser.error("No test cases selected")

    root = Path(__file__).resolve().parents[3]
    schema = json.loads((root / "semantic/ontology2/dtwise/dtwise-schema-index.json").read_text(encoding="utf-8"))
    mappings = load_cross_domain_mappings(root / "semantic/ontology2/dtwise/cross-domain-mappings.json")
    failures = 0
    start_total = perf_counter()
    for count, domains, case, check in selected:
        name, question = case[:2]
        start = perf_counter()
        raw = None
        timings = {}
        prompt_bytes = 0
        try:
            if count == 1:
                index = SubgraphIndex.from_schema_index(schema, domains[0])
                extracted = index.extract_grounded_question(question)
                prepared = prepare_candidates(extracted)
                timings["prepare"] = perf_counter() - start
                result = run_retrieve_state_machine(
                    index, prepared, model=args.model, timing=timings,
                    compile_sparql=args.emit_sparql,
                )
                selection = result["plan"]
                expected, property_name = case[2:]
                selected_paths = result["selected_paths"]
                passed = selection["status"] == expected
                if passed and expected == "selected":
                    passed = (len(selected_paths) == 1 and
                              selected_paths[0]["path"].split(" → ")[-1] == property_name)
                detail = ("Semantic assertions passed" if passed else
                          f"Expected {expected} and property {property_name}; got {selection}")
                if args.emit_sparql:
                    for query in result["queries"]:
                        print("SPARQL:\\n" + query["sparql"])
                if args.debug:
                    print("QUESTION:", question)
                    print("VALIDATED:", json.dumps(selection, ensure_ascii=False, indent=2))
                failures += not passed
                print(f"{count}D/{name}: {'PASS' if passed else 'FAIL'} {perf_counter() - start:.2f}s")
                print("TIMING:", " ".join(f"{stage}={seconds:.2f}s" for stage, seconds in timings.items()))
                print("QWEN: (handled by existing single-domain state machine)")
                if not passed or args.debug:
                    print("DETAIL:", detail)
                continue
            prepared = prepare_live_candidates(schema, mappings, question, domains)
            timings["prepare"] = perf_counter() - start
            prompt = prepared["prompt"]
            qwen_prompt = (compact_n_domain_prompt(prompt)
                           if args.prompt_format == "compact" else prompt)
            system_prompt = (COMPACT_SYSTEM_PROMPT if args.prompt_format == "compact"
                             else SYSTEM_PROMPT)
            prompt_bytes = len(json.dumps(qwen_prompt, ensure_ascii=False).encode("utf-8"))
            if args.debug:
                print("QUESTION:", question)
                print("QWEN OFFERED:", json.dumps(qwen_prompt, ensure_ascii=False, indent=2))
            if prompt["mapping_candidates"]:
                qwen_start = perf_counter()
                try:
                    raw = ollama_select(qwen_prompt, model=args.model, system_prompt=system_prompt)
                finally:
                    timings["qwen"] = perf_counter() - qwen_start
                validation_start = perf_counter()
                try:
                    selection = validate_n_domain_selection(raw, prepared)
                finally:
                    timings["validate"] = perf_counter() - validation_start
            else:
                selection = {"status": "unresolved", "result_ids": [],
                             "identifier_path_ids": [], "mapping_ids": []}
            assertion_start = perf_counter()
            passed, detail = check(selection, prompt, case)
            timings["assert"] = perf_counter() - assertion_start
            if args.debug:
                print("VALIDATED:", json.dumps(selection, ensure_ascii=False, indent=2))
            if args.emit_sparql and selection["status"] == "selected":
                sparql = compile_n_domain_sparql(selection, prepared)
                print("SPARQL:\n" + sparql)
        except Exception as exc:
            passed, detail = False, f"{type(exc).__name__}: {exc}"
        failures += not passed
        print(f"{count}D/{name}: {'PASS' if passed else 'FAIL'} {perf_counter() - start:.2f}s")
        print("TIMING:", " ".join(f"{stage}={seconds:.2f}s" for stage, seconds in timings.items()),
              f"prompt={prompt_bytes:,} bytes")
        print("QWEN:", raw if raw is not None else "(not called: no qualified mapping or request failed)")
        if not passed or args.debug:
            print("DETAIL:", detail)
    print(f"TOTAL: {'PASS' if not failures else 'FAIL'} "
          f"{len(selected) - failures}/{len(selected)} PASS, {perf_counter() - start_total:.2f}s")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
