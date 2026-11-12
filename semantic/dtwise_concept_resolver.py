"""Retrieve ontology-first concept bundles and SHACL traversal context.

Run: python -m semantic.dtwise_concept_resolver --query "ECAD device local identifier"
This module does not infer cross-domain joins or inspect instance values.
"""
import argparse
import json
import re
from collections import defaultdict, deque
from pathlib import Path


def _tokens(text):
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _local(uri):
    return re.split(r"[/#]", uri)[-1]


def _shape_graph(index):
    """Return shape links reconstructed only from indexed SHACL evidence."""
    sh = "http://www.w3.org/ns/shacl#"
    edges = defaultdict(list)
    for item in index.get("relationships", []):
        edges[(item["domain"], item["subject"], item["predicate"])].append(item)
    return edges, sh


def _traversals(index, property_uri, domain, max_depth=6):
    """Find root-to-property paths using sh:node links and sh:property ownership.

    The result is a schema path candidate, not proof that instance data
    conforms to that path or that any cross-domain join is valid.
    """
    edges, sh = _shape_graph(index)
    paths = [x for x in index.get("shape_paths", [])
             if x["domain"] == domain and x["path"] == property_uri]
    if not paths:
        return []

    # Nested shape: parent --sh:property--> propertyShape
    # propertyShape --sh:path--> predicate
    # propertyShape --sh:node--> child NodeShape.
    parents = defaultdict(list)
    for x in index.get("shape_paths", []):
        if x["domain"] != domain:
            continue
        for link in edges.get((domain, x["property_shape"], sh + "node"), []):
            parents[link["object"]].append((x["node_shape"], x["path"], x["property_shape"]))

    output = []
    for p in paths:
        start = p["node_shape"]
        queue = deque([(start, [property_uri], [p["property_shape"]], {start})])
        while queue:
            node, chain, shapes, visited = queue.popleft()
            options = sorted(parents.get(node, []))
            if not options or len(chain) >= max_depth:
                output.append({
                    "start_shape": node, "property_chain": chain,
                    "property_shapes": shapes, "complete_to_root": not options,
                })
                continue
            for parent, predicate, shape in options:
                if parent in visited:
                    continue
                queue.append((parent, [predicate] + chain,
                              [shape] + shapes, visited | {parent}))
    unique = {(x["start_shape"], tuple(x["property_chain"]),
               tuple(x["property_shapes"])): x for x in output}
    return sorted(unique.values(), key=lambda x: (len(x["property_chain"]),
                   x["property_chain"], x["start_shape"]))


DOMAIN_ALIASES = {
    "engineeringbom": {"engineeringbom", "ebom", "bom", "engineering bom"},
    "ecad": {"ecad"},
    "dexpi": {"dexpi", "p&id", "pid"},
    "assetinventory": {"assetinventory", "asset inventory"},
    "opcuaconnectivity": {"opcuaconnectivity", "opcua", "opc ua"},
    "productcatalog": {"productcatalog", "product catalog"},
}


def _mentioned_domains(question):
    normalized = " ".join(re.findall(r"[a-z0-9]+", question.lower()))
    padded = " " + normalized + " "
    found = set()
    for domain, aliases in DOMAIN_ALIASES.items():
        for alias in aliases:
            key = " ".join(re.findall(r"[a-z0-9]+", alias.lower()))
            if key and (" " + key + " ") in padded:
                found.add(domain)
                break
    return found


def resolve(index, question, limit=10):
    """Return ranked semantic concepts with their SHACL context."""
    query_tokens = _tokens(question)
    mentioned_domains = _mentioned_domains(question)
    scores = defaultdict(int)
    for token in query_tokens:
        for i in index.get("token_postings", {}).get(token, []):
            scores[i] += 1

    # Only class/property records compete for primary concept slots.
    # Shapes remain attached as evidence and traversal context.
    candidates = []
    for i, score in scores.items():
        concept = index["concepts"][i]
        if concept["kind"] not in ("property", "class"):
            continue
        local_tokens = _tokens(_local(concept["uri"]))
        label_tokens = set().union(*(_tokens(x) for x in concept["labels"])) if concept["labels"] else set()
        primary = len(query_tokens & (local_tokens | label_tokens))
        domain_match = int(concept["domain"].lower() in mentioned_domains)
        candidates.append((-(score + 2 * primary + 8 * domain_match),
                           concept["domain"], concept["uri"], concept))
    candidates.sort(key=lambda x: x[:3])

    results = []
    for neg_score, _, _, concept in candidates[:limit]:
        contexts = [x for x in index.get("shape_paths", [])
                    if x["domain"] == concept["domain"] and x["path"] == concept["uri"]]
        results.append({
            "score": -neg_score,
            "concept": concept,
            "shacl_context": contexts,
            "traversal_candidates": _traversals(index, concept["uri"], concept["domain"]),
            "cross_domain_join": "unverified",
        })
    return results


def resolve_compact(index, question, limit=10, max_paths=3):
    """Small, evidence-grounded candidate list for LLM intent selection.

    IDs are scoped to this response; they are not persistent ontology IDs.
    No identifier equality, class membership, or cross-domain join is inferred.
    """
    hits = resolve(index, question, limit=limit)
    candidates = []
    for position, hit in enumerate(hits, 1):
        concept = hit["concept"]
        traversals = hit["traversal_candidates"]
        candidates.append({
            "id": "C" + str(position),
            "score": hit["score"],
            "domain": concept["domain"],
            "kind": concept["kind"],
            "uri": concept["uri"],
            "label": concept["labels"][0] if concept["labels"] else _local(concept["uri"]),
            "paths": [{
                "property_chain": path["property_chain"],
                "start_shape": path["start_shape"],
                "complete_to_root": path["complete_to_root"],
            } for path in traversals[:max_paths]],
        })
    return {
        "question": question,
        "mentioned_domains": sorted(_mentioned_domains(question)),
        "candidates": candidates,
        "join_status": "unverified",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path,
                        default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--verbose", action="store_true", help="Show full SHACL evidence bundles")
    parser.add_argument("--max-paths", type=int, default=3)
    args = parser.parse_args()
    index = json.loads(args.index.read_text(encoding="utf-8"))
    result = (resolve(index, args.query, args.limit) if args.verbose else
              resolve_compact(index, args.query, args.limit, args.max_paths))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
