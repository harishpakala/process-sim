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


def resolve(index, question, limit=10):
    """Return ranked semantic concepts with their SHACL context."""
    query_tokens = _tokens(question)
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
        domain_match = int(concept["domain"].lower() in query_tokens)
        candidates.append((-(score + 2 * primary + 2 * domain_match),
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path,
                        default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    index = json.loads(args.index.read_text(encoding="utf-8"))
    print(json.dumps(resolve(index, args.query, args.limit), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
