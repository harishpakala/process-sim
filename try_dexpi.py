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
        "--domain", default="dexpi",
        help="Single schema domain in the index (default: dexpi; e.g. ecad)",
    )
    parser.add_argument("--llm", action="store_true", help="Use local Ollama")
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
    question = args.question or DEFAULT_QUESTIONS.get(args.domain)
    if question is None:
        parser.error("Supply a question for this domain")

    index = load_index(args.index, domain=args.domain)
    if args.semantic_paths and args.semantic:
        parser.error("--semantic-paths and --semantic are separate modes")
    if args.grouped and not args.semantic:
        parser.error("--grouped requires --semantic")
    if args.semantic and args.llm:
        parser.error("--semantic and --llm are separate experiments")
    if args.semantic_paths:
        from process_sim.dtwise.experimental_shacl_semantic_candidates import semantic_candidates
        prepared = semantic_candidates(index, question, top_shapes=args.top_k,
                                       model=args.embed_model, endpoint=args.ollama_url)
        if args.llm:
            from process_sim.dtwise.experimental_shacl_ollama import ollama_select
            from process_sim.dtwise.experimental_shacl_selection import validate_selection
            if prepared["prompt"]["candidates"]:
                raw = ollama_select(prepared["prompt"], model=args.model,
                                    endpoint=args.ollama_url)
                selection = validate_selection(raw, prepared)
            else:
                selection = {"status": "unresolved", "selected_candidate_ids": [],
                             "reason": "No verified semantic candidates"}
            result = {"selection": selection,
                      "selected_paths": [
                          candidate for candidate in prepared["prompt"]["candidates"]
                          if candidate["id"] in selection["selected_candidate_ids"]
                      ], "prepared": prepared}
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
