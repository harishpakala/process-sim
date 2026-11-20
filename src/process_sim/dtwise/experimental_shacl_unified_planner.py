"""Unified import-only entry point for existing single- and multi-domain SHACL planners.

Single-domain operation is classified when omitted; explicit overrides remain supported.
SPARQL is compiled, never executed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from process_sim.dtwise.shacl_planner.multi_domain.cross_domain_mappings import load_cross_domain_mappings
from process_sim.dtwise.shacl_planner.query_classifier import classify_single_domain_query
from process_sim.dtwise.shacl_planner.multi_domain.domain_resolution import resolve_domain, resolve_domains
from process_sim.dtwise.experimental_shacl_n_domain_live import prepare_live_candidates
from process_sim.dtwise.experimental_shacl_n_domain_selection import (
    SYSTEM_PROMPT, COMPACT_SYSTEM_PROMPT, compact_n_domain_prompt,
    validate_n_domain_selection,
)
from process_sim.dtwise.experimental_shacl_n_domain_sparql import compile_n_domain_sparql
from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError
from process_sim.dtwise.shacl_planner.grounding.subgraph import load_index
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


def plan_question(question: str, schema: dict, mappings: dict, *, domains: int | None = None,
                  operation: str | None = None, model: str = "qwen2.5-coder:7b",
                  embed_model: str = "nomic-embed-text:latest",
                  ollama_url: str = "http://127.0.0.1:11434",
                  prompt_format: str = "compact",
                  domain: str | None = None, index_path: Path | None = None,
                  timing: bool = False) -> dict:
    """Route by detected domains when no explicit domain count is supplied."""
    timings = {} if timing else None
    started = perf_counter()

    def finish(result):
        if timings is not None:
            timings["total_ms"] = (perf_counter() - started) * 1000
            result["timing_ms"] = timings
        return result

    if not question.strip():
        raise ValueError("Question must not be empty")
    available = {
        item["domain"] for key in ("concepts", "shape_paths")
        for item in schema.get(key, []) if item.get("domain")
    }
    t0 = perf_counter()
    if domains is None:
        selected_domains = resolve_domains(question, available, schema=schema)
    elif isinstance(domains, int) and domains in (1, 2, 3, 4):
        selected_domains = (resolve_domain(question, available, override=domain, schema=schema),) if domains == 1 else DOMAIN_SETS[domains]
    else:
        raise ValueError("domains must be 1, 2, 3, or 4, or None")
    if timings is not None:
        timings["domain_resolution_ms"] = (perf_counter() - t0) * 1000
    domains = len(selected_domains)
    if domains == 1:
        classification = None
        if operation is None:
            try:
                t0 = perf_counter()
                classification = classify_single_domain_query(
                    question, model=model, endpoint=ollama_url)
                if timings is not None:
                    timings["query_classification_ms"] = (perf_counter() - t0) * 1000
            except ValueError as exc:
                return finish({"mode": "single-domain", "operation": None,
                        "classification": {"status": "unsupported",
                                           "operation": None, "reason": str(exc)},
                        "sparql": None})
            if classification["status"] == "unsupported":
                return finish({"mode": "single-domain", "operation": None,
                        "classification": classification, "sparql": None})
            operation = classification["operation"]
        if operation not in OPERATIONS:
            raise ValueError(f"Unsupported single-domain operation: {operation}")
        if index_path is None:
            raise ValueError("Single-domain planning requires index_path")
        chosen_domain = resolve_domain(question, available, override=domain, schema=schema) if domain else selected_domains[0]
        t0 = perf_counter()
        index = load_index(index_path, domain=chosen_domain)
        if timings is not None:
            timings["index_loading_ms"] = (perf_counter() - t0) * 1000
        from process_sim.dtwise.try_dexpi import run_single_domain_query
        result = run_single_domain_query(
            index, question, operation=operation, model=model,
            embed_model=embed_model, endpoint=ollama_url, timing=timings,
        )
        return finish({"mode": "single-domain", "operation": operation,
                **({"classification": classification} if classification else {}), **result})

    t0 = perf_counter()
    prepared = prepare_live_candidates(schema, mappings, question, selected_domains)
    if timings is not None:
        timings["multi_domain_candidate_preparation_ms"] = (perf_counter() - t0) * 1000
    prompt = prepared["prompt"]
    if not prompt["mapping_candidates"]:
        return finish({
            "mode": "n-domain", "domains": selected_domains,
            "selection": {"status": "unresolved", "result_ids": [],
                          "identifier_path_ids": [], "mapping_ids": []},
            "sparql": None,
        })
    compact = prompt_format == "compact"
    t0 = perf_counter()
    raw = ollama_select(
        compact_n_domain_prompt(prompt) if compact else prompt,
        model=model, endpoint=ollama_url,
        system_prompt=COMPACT_SYSTEM_PROMPT if compact else SYSTEM_PROMPT,
    )
    if timings is not None:
        timings["qwen_selection_ms"] = (perf_counter() - t0) * 1000
    t0 = perf_counter()
    try:
        selection = validate_n_domain_selection(raw, prepared)
    except SelectionContractError as exc:
        if timings is not None:
            timings["python_validation_ms"] = (perf_counter() - t0) * 1000
        return finish({
            "mode": "n-domain", "domains": selected_domains,
            "error": {"type": type(exc).__name__, "message": str(exc)},
            "raw_model_response": raw, "sparql": None,
        }))
    if timings is not None:
        timings["python_validation_ms"] = (perf_counter() - t0) * 1000
    t0 = perf_counter()
    sparql = (compile_n_domain_sparql(selection, prepared)
              if selection["status"] == "selected" else None)
    if timings is not None:
        timings["sparql_compilation_ms"] = (perf_counter() - t0) * 1000
    return finish({"mode": "n-domain", "domains": selected_domains,
                   "selection": selection, "sparql": sparql})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--domains", type=int, choices=(1, 2, 3, 4),
                        help="Optional domain-count override; inferred when omitted")
    parser.add_argument("--domain", help="Optional single-domain override")
    parser.add_argument("--operation", choices=OPERATIONS, default=None,
                        help="Optional single-domain operation override; inferred when omitted")
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument("--embed-model", default="nomic-embed-text:latest")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--prompt-format", choices=("compact", "full"), default="compact")
    parser.add_argument("--timing", action="store_true", help="Include planner stage timings")
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
        timing=args.timing,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
