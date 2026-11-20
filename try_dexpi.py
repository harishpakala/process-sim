"""Run a manual single-domain SHACL subgraph extraction smoke test.

From the repository root:
    python -m pip install -e .
    python try_dexpi.py --domain ecad --connect "Show Address in ECAD"
    python try_dexpi.py --domain ecad --connect --json "Show Address in ECAD"

Compact output is the default; --json prints the full evidence-rich result.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from time import perf_counter

from process_sim.dtwise.experimental_shacl_domain_resolution import (
    DomainResolutionError, resolve_domain,
)

from process_sim.dtwise.experimental_shacl_subgraph import (
    extract_question,
    load_index,
)

DEFAULT_QUESTIONS = {
    "dexpi": (
        "Show the MeasuredVariable of InstrumentationFunction "
        "and the ActuatedVariable of ActuatingFunction"
    ),
    "ecad": "Show Address of EndPoint belonging to Device in ECAD",
}


def format_compact(result: dict) -> str:
    """Display paths and ambiguity without repeating verbose SHACL URIs."""
    names = {node["uri"]: node["name"] for node in result["nodes"]}
    outgoing = defaultdict(list)
    for edge in result["edges"]:
        outgoing[edge["from"]].append(edge)
    for edges in outgoing.values():
        edges.sort(key=lambda edge: (names.get(edge["to"], ""), edge["predicate"]))

    def path(start: str, target: str) -> list[str] | None:
        queue = [(start, [start])]
        seen = {start}
        while queue:
            current, chain = queue.pop(0)
            if current == target:
                return [names.get(uri, uri) for uri in chain]
            for edge in outgoing[current]:
                nxt = edge["to"]
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append((nxt, chain + [nxt]))
        return None

    alternatives = result.get("ambiguous_paths", [])
    shared = result.get("shared_context")
    status = (
        "AMBIGUOUS" if alternatives else
        "UNRESOLVED" if result["unresolved_connections"] else
        "SHARED CONTEXT" if shared else "GROUNDED"
    )
    lines = [
        f'Question: {result["question"]}',
        f'Domain: {result["domain"].upper()}',
        f'Status: {status}',
        "",
        "Paths:",
    ]
    if alternatives:
        entries = []
        for alternative in alternatives:
            target = alternative["target"]
            chain = path(alternative["start"], target)
            for prop in result["properties"]:
                if prop["owner"] == target:
                    entries.append((chain or [names.get(target, target)]) + [prop["name"]])
        for number, entry in enumerate(entries, 1):
            lines.append(f'  {number}. {" → ".join(entry)}')
    else:
        roots = {edge["from"] for edge in result["edges"]} - {
            edge["to"] for edge in result["edges"]
        }
        entries = []
        for prop in result["properties"]:
            owner = prop["owner"]
            chains = [path(root, owner) for root in sorted(roots)]
            chain = next((candidate for candidate in chains if candidate), None)
            entries.append((chain or [names.get(owner, owner)]) + [prop["name"]])
        if not entries:
            entries = [[names.get(uri, uri)] for uri in sorted(names)]
        for number, entry in enumerate(entries, 1):
            lines.append(f'  {number}. {" → ".join(entry)}')
    lines += [
        "",
        "Summary:",
        f'  Nodes: {len(result["nodes"])}',
        f'  Edges: {len(result["edges"])}',
        f'  Properties: {len(result["properties"])}',
        f'  Alternatives: {len(alternatives)}',
        f'  Unresolved: {len(result["unresolved_connections"])}',
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="?", help="Natural-language schema question")
    parser.add_argument(
        "--domain", default=None,
        help="Optional schema domain override (otherwise resolved from question)",
    )
    parser.add_argument("--llm", action="store_true", help="Use local Ollama")
    parser.add_argument("--sparql", action="store_true", help="Compile selected verified paths (requires --semantic-paths --llm)")
    parser.add_argument("--direct-intent", action="store_true", help="Opt-in direct Ollama structured ECAD join intent; independently validate and compile only")
    parser.add_argument("--phase4-and-join", action="store_true", help="Opt-in same-Device ECAD Address join with LocalId AND DeviceType filters; compile only")
    parser.add_argument("--phase4-filtered-join", action="store_true", help="Opt-in same-Device ECAD Address join with one Device.LocalId equality; compile only")
    parser.add_argument("--phase4-join", action="store_true", help="Opt-in same-Device ECAD sibling Address join; compile only")
    parser.add_argument("--phase3-and", action="store_true", help="Opt-in RETRIEVE with two AND string equality filters; compile only")
    parser.add_argument("--phase2-filter", action="store_true", help="Opt-in RETRIEVE with one string equality filter; compile SPARQL only")
    parser.add_argument("--phase1-sparql", action="store_true", help="Compile Phase 1 verified RETRIEVE paths to read-only SPARQL (not executed)")
    parser.add_argument("--timing", action="store_true", help="Show stage latency for --phase1-plan")
    parser.add_argument("--phase1-plan", action="store_true", help="Opt-in Qwen intent and qualified path selection (requires --semantic-paths --llm; no SPARQL)")
    parser.add_argument("--semantic", action="store_true", help="Rank schema terms using local embeddings")
    parser.add_argument("--semantic-paths", action="store_true", help="Build verified paths from semantic rankings; optionally use --llm")
    parser.add_argument("--grouped", action="store_true", help="Separate shape/property ranks and group duplicate labels (requires --semantic)")
    parser.add_argument("--embed-model", default="nomic-embed-text:latest")
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument(
        "--connect", action="store_true",
        help="Attempt verified directed SHACL connections",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="Print full diagnostic JSON")
    output.add_argument("--compact", action="store_true", help="Print concise paths (default)")
    parser.add_argument(
        "--index", type=Path,
        default=Path(__file__).resolve().parent
        / "semantic/ontology2/dtwise/dtwise-schema-index.json",
    )
    args = parser.parse_args()
    # Preserve the no-argument manual smoke test; all supplied questions must
    # resolve a domain explicitly or use --domain.
    question = args.question or DEFAULT_QUESTIONS.get(args.domain or "dexpi")
    if question is None:
        parser.error("Supply a question for this domain")
    if args.question is None and args.domain is None:
        args.domain = "dexpi"
    try:
        with args.index.open(encoding="utf-8") as source:
            schema = json.load(source)
        available_domains = {
            item["domain"] for key in ("concepts", "shape_paths")
            for item in schema.get(key, []) if item.get("domain")
        }
        args.domain = resolve_domain(question, available_domains, override=args.domain, schema=schema)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))

    if args.direct_intent and (not args.semantic_paths or not args.llm or args.phase4_and_join or args.phase4_filtered_join or args.phase4_join or args.phase3_and or args.phase2_filter or args.phase1_plan or args.phase1_sparql or args.sparql):
        parser.error("--direct-intent requires --semantic-paths --llm and excludes other plan/SPARQL modes")
    if args.phase4_and_join and (not args.semantic_paths or not args.llm or args.phase4_filtered_join or args.phase4_join or args.phase3_and or args.phase2_filter or args.phase1_plan or args.phase1_sparql or args.sparql):
        parser.error("--phase4-and-join requires --semantic-paths --llm and excludes other plan/SPARQL modes")
    if args.phase4_filtered_join and (not args.semantic_paths or not args.llm or args.phase4_join or args.phase3_and or args.phase2_filter or args.phase1_plan or args.phase1_sparql or args.sparql or args.phase4_and_join):
        parser.error("--phase4-filtered-join requires --semantic-paths --llm and excludes other plan/SPARQL modes")
    if args.phase4_join and (not args.semantic_paths or not args.llm or args.phase3_and or args.phase2_filter or args.phase1_plan or args.phase1_sparql or args.sparql or args.phase4_filtered_join or args.phase4_and_join):
        parser.error("--phase4-join requires --semantic-paths --llm and excludes other plan/SPARQL modes")
    if args.phase3_and and (not args.semantic_paths or not args.llm or args.phase2_filter or args.phase1_plan or args.phase1_sparql or args.sparql or args.phase4_join or args.phase4_filtered_join or args.phase4_and_join):
        parser.error("--phase3-and requires --semantic-paths --llm and excludes other plan/SPARQL modes")
    if args.phase2_filter and (not args.semantic_paths or not args.llm or args.phase1_plan or args.phase1_sparql or args.sparql or args.phase3_and or args.phase4_join or args.phase4_filtered_join or args.phase4_and_join):
        parser.error("--phase2-filter requires --semantic-paths --llm and excludes other plan/SPARQL modes")
    if args.phase1_sparql and not args.phase1_plan:
        parser.error("--phase1-sparql requires --phase1-plan")
    if args.timing and not args.phase1_plan:
        parser.error("--timing currently requires --phase1-plan")
    t_total = perf_counter()
    t_index = perf_counter()
    index = load_index(args.index, domain=args.domain)
    timings = {"index_loading_ms": (perf_counter() - t_index) * 1000} if args.timing else None
    if args.phase1_plan and (not args.semantic_paths or not args.llm or args.sparql):
        parser.error("--phase1-plan requires --semantic-paths --llm and excludes --sparql")
    if args.sparql and not (args.semantic_paths and args.llm):
        parser.error("--sparql requires --semantic-paths --llm")
    if args.semantic_paths and args.semantic:
        parser.error("--semantic-paths and --semantic are separate modes")
    if args.grouped and not args.semantic:
        parser.error("--grouped requires --semantic")
    if args.semantic and args.llm:
        parser.error("--semantic and --llm are separate experiments")
    if args.semantic_paths:
        from process_sim.dtwise.experimental_shacl_grounding import (
            property_grounding, enforce_property_grounding,
        )
        grounding = property_grounding(index, question)
        if grounding["missing_properties"]:
            selection = {
                "status": "unresolved", "selected_candidate_ids": [],
                "reason": "Explicit SHACL property not found in domain: "
                          + ", ".join(grounding["missing_properties"]),
            }
            if args.json:
                print(json.dumps({"selection": selection, "selected_paths": [],
                                  "grounding": grounding}, indent=2))
            else:
                print("Question:", question)
                print("Domain:", args.domain.upper())
                print("Status: UNRESOLVED")
                print("Reason:", selection["reason"])
                print("Selected paths:")
                print("  (none)")
            return
        from process_sim.dtwise.experimental_shacl_semantic_candidates import semantic_candidates
        t_retrieval = perf_counter()
        prepared = semantic_candidates(index, question, top_shapes=max(args.top_k, 16) if (args.phase2_filter or args.phase4_join or args.phase4_filtered_join or args.phase4_and_join or args.direct_intent) else args.top_k,
                                       top_properties=8 if (args.phase2_filter or args.phase3_and or args.phase4_join or args.phase4_filtered_join or args.phase4_and_join or args.direct_intent) else 2,
                                       max_candidates=128 if (args.phase2_filter or args.phase3_and or args.phase4_join or args.phase4_filtered_join or args.phase4_and_join or args.direct_intent) else 64,
                                       model=args.embed_model, endpoint=args.ollama_url)
        if timings is not None:
            timings["semantic_retrieval_ms"] = (perf_counter() - t_retrieval) * 1000
        if args.direct_intent:
            from process_sim.dtwise.experimental_shacl_query_intent import run_direct_join_intent
            result = run_direct_join_intent(index, prepared, model=args.model,
                                            endpoint=args.ollama_url)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Question:", question)
                print("Domain:", args.domain.upper())
                print("Status:", "SELECTED" if result["intent"] is not None else "UNRESOLVED")
                if result["intent"] is not None:
                    print("Validated structured intent:")
                    print(json.dumps(result["intent"], indent=2, ensure_ascii=False))
                else:
                    print("Reason:", result.get("reason", "No validated intent"))
                print("Compiled SPARQL (not executed):")
                print(result["sparql"] or "  (none)")
        elif args.phase4_and_join:
            from process_sim.dtwise.experimental_shacl_planner_state_machine import (
                run_join_state_machine,
            )
            result = run_join_state_machine(index, prepared, model=args.model,
                                            endpoint=args.ollama_url)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Question:", question)
                print("Domain:", args.domain.upper())
                print("Status:", result["plan"]["status"].upper())
                print("Reason:", result["plan"]["reason"])
                print("Compiled SPARQL (not executed):")
                print(result["sparql"] or "  (none)")
        elif args.phase4_filtered_join:
            from process_sim.dtwise.experimental_shacl_phase4_filtered_join import (
                run_phase4_filtered_join_plan, compile_phase4_filtered_join_sparql,
            )
            result = run_phase4_filtered_join_plan(index, prepared, model=args.model,
                                                   endpoint=args.ollama_url)
            result["sparql"] = compile_phase4_filtered_join_sparql(result)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Question:", question)
                print("Domain:", args.domain.upper())
                print("Status:", result["plan"]["status"].upper())
                print("Reason:", result["plan"]["reason"])
                print("Compiled SPARQL (not executed):")
                print(result["sparql"] or "  (none)")
        elif args.phase4_join:
            from process_sim.dtwise.experimental_shacl_phase4_join import (
                run_phase4_join_plan, compile_phase4_join_sparql,
            )
            result = run_phase4_join_plan(index, prepared, model=args.model,
                                          endpoint=args.ollama_url)
            result["sparql"] = compile_phase4_join_sparql(result)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Question:", question)
                print("Domain:", args.domain.upper())
                print("Status:", result["plan"]["status"].upper())
                print("Reason:", result["plan"]["reason"])
                print("Compiled SPARQL (not executed):")
                print(result["sparql"] or "  (none)")
        elif args.phase3_and:
            from process_sim.dtwise.experimental_shacl_phase3_and import (
                run_phase3_and_plan, compile_phase3_and_sparql,
            )
            result = run_phase3_and_plan(index, prepared, model=args.model,
                                         endpoint=args.ollama_url)
            result["sparql"] = compile_phase3_and_sparql(result)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Question:", question)
                print("Domain:", args.domain.upper())
                print("Status:", result["plan"]["status"].upper())
                print("Reason:", result["plan"]["reason"])
                print("Compiled SPARQL (not executed):")
                if isinstance(result["sparql"], dict):
                    for rid, query in result["sparql"].items():
                        print(f"  {rid}:")
                        print(query)
                else:
                    print(result["sparql"] or "  (none)")
        elif args.phase2_filter:
            from process_sim.dtwise.experimental_shacl_phase2_filter import (
                run_phase2_filter_plan, compile_phase2_filter_sparql,
            )
            result = run_phase2_filter_plan(index, prepared, model=args.model,
                                            endpoint=args.ollama_url)
            result["queries"] = compile_phase2_filter_sparql(result)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Question:", question)
                print("Domain:", args.domain.upper())
                print("Status:", result["plan"]["status"].upper())
                print("Reason:", result["plan"]["reason"])
                print("Compiled SPARQL (not executed):")
                for item in result["queries"]:
                    print(" ", item["result_id"] + " filtered by " + item["filter_id"] + ":")
                    print(item["sparql"])
                if not result["queries"]:
                    print("  (none)")
        elif args.phase1_plan:
            from process_sim.dtwise.experimental_shacl_planner_state_machine import (
                run_retrieve_state_machine,
            )
            result = run_retrieve_state_machine(
                index, prepared, model=args.model, endpoint=args.ollama_url,
                timing=timings, compile_sparql=args.phase1_sparql,
            )
            if timings is not None:
                timings["total_ms"] = (perf_counter() - t_total) * 1000
                result["timing_ms"] = timings
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Question:", question)
                print("Domain:", args.domain.upper())
                print("Status:", result["plan"]["status"].upper())
                print("Operation:", result["plan"]["operation"])
                print("Reason:", result["plan"]["reason"])
                print("Selected qualified paths:")
                for item in result["selected_paths"]:
                    print(" ", item["id"] + ".", item["path"])
                if not result["selected_paths"]:
                    print("  (none)")
                if args.phase1_sparql:
                    print("Compiled SPARQL (not executed):")
                    for item in result["queries"]:
                        print(" ", item["candidate_id"] + ":")
                        print(item["sparql"])
                    if not result["queries"]:
                        print("  (none)")
                if timings is not None:
                    print("Timing (ms):")
                    for key, value in timings.items():
                        print(f"  {key}: {value:.1f}")
        elif args.llm:
            from process_sim.dtwise.experimental_shacl_ollama import ollama_select
            from process_sim.dtwise.experimental_shacl_selection import validate_selection
            if prepared["prompt"]["candidates"]:
                raw = ollama_select(prepared["prompt"], model=args.model,
                                    endpoint=args.ollama_url)
                selection = enforce_property_grounding(
                    index, question, prepared, validate_selection(raw, prepared),
                )
            else:
                selection = {"status": "unresolved", "selected_candidate_ids": [],
                             "reason": "No verified semantic candidates"}
            result = {"selection": selection,
                      "selected_paths": [
                          candidate for candidate in prepared["prompt"]["candidates"]
                          if candidate["id"] in selection["selected_candidate_ids"]
                      ], "prepared": prepared}
            if args.sparql:
                from process_sim.dtwise.experimental_shacl_sparql import compile_selected_paths
                result["queries"] = compile_selected_paths(prepared, selection)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print("Question:", question)
                print("Domain:", args.domain.upper())
                print("Status:", selection["status"].upper())
                print("Reason:", selection["reason"])
                print("Selected paths:")
                for candidate in result["selected_paths"]:
                    print(" ", candidate["id"] + ".", candidate["path"])
                if not result["selected_paths"]:
                    print("  (none)")
                if args.sparql:
                    print("Compiled SPARQL (not executed):")
                    for item in result["queries"]:
                        print(" ", item["candidate_id"] + ":")
                        print(item["sparql"])
                    if not result["queries"]:
                        print("  (none)")
        elif args.json:
            print(json.dumps(prepared, indent=2, ensure_ascii=False))
        else:
            print("Question:", question)
            print("Domain:", args.domain.upper())
            print("Verified semantic candidates (not yet selected):")
            for candidate in prepared["prompt"]["candidates"]:
                print(" ", candidate["id"] + ".", candidate["path"])
            if not prepared["prompt"]["candidates"]:
                print("  (none)")
    elif args.semantic:
        from process_sim.dtwise.experimental_shacl_semantic import semantic_grouped, semantic_terms
        search = semantic_grouped if args.grouped else semantic_terms
        result = search(index, question, top_k=args.top_k,
                        model=args.embed_model, endpoint=args.ollama_url)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("Question:", question)
            print("Domain:", args.domain.upper())
            print("Embedding model:", args.embed_model)
            print("Semantic matches (suggestions only; no paths selected):")
            if args.grouped:
                for kind, key in (("Shapes", "shapes"), ("Properties", "properties")):
                    print(kind + ":")
                    for item in result[key]:
                        print(" ", item["score"], item["label"],
                              "(" + str(len(item["members"])) + " SHACL references)")
            else:
                for item in result["matches"]:
                    print(" ", item["score"], item["kind"], item["label"])
    elif args.llm:
        from process_sim.dtwise.experimental_shacl_ollama import run_local_selection
        result = run_local_selection(index, question, model=args.model, endpoint=args.ollama_url)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            selection = result["selection"]
            print("Question:", question)
            print("Domain:", args.domain.upper())
            print("Model:", args.model)
            print("Status:", selection["status"].upper())
            print("Reason:", selection["reason"])
            print("Selected paths:")
            for item in result["selected_paths"]:
                print(" ", item["id"] + ".", item["path"])
            if not result["selected_paths"]:
                print("  (none)")
    else:
        result = extract_question(index, question, connect=args.connect)
        print(json.dumps(result, indent=2) if args.json else format_compact(result))


if __name__ == "__main__":
    main()
