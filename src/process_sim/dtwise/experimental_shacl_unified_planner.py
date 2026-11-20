"""Import-only orchestration of the existing experimental SHACL planners.

No subprocesses, new selection rules, or changes to existing planners.
The caller explicitly supplies domains and (for single-domain questions)
an existing operation name. Unsupported/ambiguous plans are returned as-is.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from process_sim.dtwise.experimental_shacl_candidates import prepare_candidates
from process_sim.dtwise.experimental_shacl_cross_domain_mappings import load_cross_domain_mappings
from process_sim.dtwise.experimental_shacl_n_domain_live import prepare_live_candidates
from process_sim.dtwise.experimental_shacl_n_domain_selection import (
    COMPACT_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    compact_n_domain_prompt,
    validate_n_domain_selection,
)
from process_sim.dtwise.experimental_shacl_n_domain_sparql import compile_n_domain_sparql
from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_planner_state_machine import (
    run_single_domain_state_machine,
)
from process_sim.dtwise.experimental_shacl_subgraph import SubgraphIndex


def plan_question(
    question: str,
    domains: tuple[str, ...],
    schema: dict,
    mappings: dict,
    *,
    model: str = "qwen2.5-coder:7b",
    prompt_format: str = "compact",
    operation: str = "phase1-plan",
) -> dict:
    """Delegate to existing single-domain or N-domain planning functions.

    Domain selection and single-domain operation selection are explicit:
    this module does not add a new intent classifier or domain router.
    """
    if not question.strip():
        raise ValueError("Question must not be empty")
    if not domains or len(set(domains)) != len(domains):
        raise ValueError("Provide one or more distinct domains")
    if prompt_format not in ("compact", "full"):
        raise ValueError("prompt_format must be compact or full")

    if len(domains) == 1:
        index = SubgraphIndex.from_schema_index(schema, domains[0])
        extracted = index.extract_grounded_question(question)
        prepared = prepare_candidates(extracted)
        result = run_single_domain_state_machine(
            index, prepared, operation=operation, model=model,
        )
        return {"mode": "single-domain", "result": result}

    prepared = prepare_live_candidates(schema, mappings, question, domains)
    prompt = prepared["prompt"]
    if not prompt["mapping_candidates"]:
        return {
            "mode": "n-domain",
            "selection": {
                "status": "unresolved",
                "result_ids": [],
                "identifier_path_ids": [],
                "mapping_ids": [],
                "reason": "No qualified identifier bridge candidates",
            },
            "sparql": None,
        }
    compact = prompt_format == "compact"
    raw = ollama_select(
        compact_n_domain_prompt(prompt) if compact else prompt,
        model=model,
        system_prompt=COMPACT_SYSTEM_PROMPT if compact else SYSTEM_PROMPT,
    )
    selection = validate_n_domain_selection(raw, prepared)
    sparql = (
        compile_n_domain_sparql(selection, prepared)
        if selection["status"] == "selected" else None
    )
    return {"mode": "n-domain", "selection": selection, "sparql": sparql}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified experimental SHACL planner")
    parser.add_argument("question", help="Natural-language question")
    parser.add_argument("--domains", nargs="+", required=True,
                        help="Explicit schema domains, e.g. dexpi ecad assetinventory")
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument("--prompt-format", choices=("compact", "full"), default="compact")
    parser.add_argument("--operation", default="phase1-plan",
                        help="Existing single-domain operation (default: phase1-plan)")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    schema = json.loads(
        (root / "semantic/ontology2/dtwise/dtwise-schema-index.json").read_text(encoding="utf-8")
    )
    mappings = load_cross_domain_mappings(
        root / "semantic/ontology2/dtwise/cross-domain-mappings.json"
    )
    result = plan_question(
        args.question, tuple(args.domains), schema, mappings,
        model=args.model, prompt_format=args.prompt_format, operation=args.operation,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
