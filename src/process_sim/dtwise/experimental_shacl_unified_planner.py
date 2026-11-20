"""Unified import-only entry point for existing single- and multi-domain SHACL planners.

Operation selection is explicit; no new intent classifier or validation rules.
SPARQL is compiled, never executed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from process_sim.dtwise.experimental_shacl_cross_domain_mappings import load_cross_domain_mappings
from process_sim.dtwise.experimental_shacl_domain_resolution import resolve_domain
from process_sim.dtwise.experimental_shacl_n_domain_live import prepare_live_candidates
from process_sim.dtwise.experimental_shacl_n_domain_selection import (
    SYSTEM_PROMPT, COMPACT_SYSTEM_PROMPT, compact_n_domain_prompt,
    validate_n_domain_selection,
)
from process_sim.dtwise.experimental_shacl_n_domain_sparql import compile_n_domain_sparql
from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.experimental_shacl_subgraph import load_index
from process_sim.dtwise.experimental_shacl_three_domain_integration import DOMAINS as THREE_DOMAINS
from process_sim.dtwise.experimental_shacl_four_domain_integration import DOMAINS as FOUR_DOMAINS

DOMAIN_SETS = {
    2: ("dexpi", "ecad"),
    3: THREE_DOMAINS,
    4: FOUR_DOMAINS,
}
OPERATIONS = (
    "phase1-plan", "phase2-filter", "phase3-and", "phase4-join",
    "phase4-filtered-join", "phase4-and-join", "direct-intent",
)


def plan_question(question: str, schema: dict, mappings: dict, *, domains: int,
                  operation: str = "phase1-plan", model: str = "qwen2.5-coder:7b",
                  embed_model: str = "nomic-embed-text:latest",
                  ollama_url: str = "http://127.0.0.1:11434",
                  prompt_format: str = "compact",
                  domain: str | None = None, index_path: Path | None = None) -> dict:
    """Call the established planning functions without a subprocess or new routing logic."""
    if not question.strip():
        raise ValueError("Question must not be empty")
    if domains not in (1, 2, 3, 4):
        raise ValueError("domains must be 1, 2, 3, or 4")
    if domains == 1:
        if operation not in OPERATIONS:
            raise ValueError(f"Unsupported single-domain operation: {operation}")
        if index_path is None:
            raise ValueError("Single-domain planning requires index_path")
        available = {
            item["domain"] for key in ("concepts", "shape_paths")
            for item in schema.get(key, []) if item.get("domain")
        }
        chosen_domain = resolve_domain(question, available, override=domain, schema=schema)
        index = load_index(index_path, domain=chosen_domain)
        from try_dexpi import run_single_domain_query
        result = run_single_domain_query(
            index, question, operation=operation, model=model,
            embed_model=embed_model, endpoint=ollama_url,
        )
        return {"mode": "single-domain", "operation": operation, **result}

    selected_domains = DOMAIN_SETS[domains]
    prepared = prepare_live_candidates(schema, mappings, question, selected_domains)
    prompt = prepared["prompt"]
    if not prompt["mapping_candidates"]:
        return {
            "mode": "n-domain", "domains": selected_domains,
            "selection": {"status": "unresolved", "result_ids": [],
                          "identifier_path_ids": [], "mapping_ids": []},
            "sparql": None,
        }
    compact = prompt_format == "compact"
    raw = ollama_select(
        compact_n_domain_prompt(prompt) if compact else prompt,
        model=model, endpoint=ollama_url,
        system_prompt=COMPACT_SYSTEM_PROMPT if compact else SYSTEM_PROMPT,
    )
    try:
        selection = validate_n_domain_selection(raw, prepared)
    except SelectionContractError as exc:
        return {
            "mode": "n-domain", "domains": selected_domains,
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "raw_model_response": raw, "sparql": None,
        }
    return {
        "mode": "n-domain", "domains": selected_domains, "selection": selection,
        "sparql": (compile_n_domain_sparql(selection, prepared)
                   if selection["status"] == "selected" else None),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--domains", type=int, required=True, choices=(1, 2, 3, 4))
    parser.add_argument("--domain", help="Optional single-domain override")
    parser.add_argument("--operation", choices=OPERATIONS, default="phase1-plan",
                        help="Existing single-domain operation; explicit, not inferred")
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument("--embed-model", default="nomic-embed-text:latest")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--prompt-format", choices=("compact", "full"), default="compact")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[3]
    index_path = root / "semantic/ontology2/dtwise/dtwise-schema-index.json"
    schema = json.loads(index_path.read_text(encoding="utf-8"))
    mappings = load_cross_domain_mappings(
        root / "semantic/ontology2/dtwise/cross-domain-mappings.json"
    )
    result = plan_question(
        args.question, schema, mappings, domains=args.domains,
        operation=args.operation, domain=args.domain, model=args.model,
        embed_model=args.embed_model, ollama_url=args.ollama_url,
        prompt_format=args.prompt_format, index_path=index_path,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
