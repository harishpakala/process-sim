"""Compile a validated DTWise semantic selection to a single-domain SPARQL query.

Run: python -m semantic.dtwise_sparql_compiler --query "ECAD device local identifier"
This module never synthesizes cross-domain joins or SHACL hierarchy FILTERs.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from semantic.dtwise_concept_resolver import _tokens
from semantic.dtwise_intent_selector import select_intent


def _iri(value):
    if not isinstance(value, str) or not value.startswith(("http://", "https://")):
        raise ValueError("Unsupported ontology IRI: " + repr(value))
    if any(char in value for char in '<>"{}|^\\\x00\n\r\t '):
        raise ValueError("Unsafe ontology IRI")
    parsed = urlsplit(value)
    if not parsed.netloc:
        raise ValueError("Ontology IRI must be absolute")
    return "<" + value + ">"


def _choose_path(concept, question):
    paths = [p for p in concept.get("paths", [])
             if p.get("complete_to_root") and p.get("property_chain")]
    if not paths:
        raise ValueError("No complete SHACL traversal for " + concept["uri"])
    question_tokens = _tokens(question)
    def rank(path):
        # Match the *intermediate* structure: device vs symbol vs endpoint.
        intermediates = path["property_chain"][:-1]
        words = set().union(*(_tokens(x.rsplit("/", 1)[-1]) for x in intermediates))
        return (-len(words & question_tokens), len(intermediates),
                tuple(path["property_chain"]))
    return min(paths, key=rank)


def compile_sparql(selection, limit=100):
    if not isinstance(limit, int) or not 1 <= limit <= 10000:
        raise ValueError("LIMIT must be between 1 and 10000")
    selected = selection.get("selected_concepts", [])
    if len(selected) != 1:
        raise ValueError("Single-property compilation requires exactly one selected concept")
    concept = selected[0]
    if concept.get("kind") != "property":
        raise ValueError("Only property concepts are supported")
    if selection.get("value_constraints"):
        raise ValueError("Value constraints require an explicit grounded predicate/value planner")
    if selection.get("join_status") != "unverified":
        raise ValueError("Unexpected join status; compiler does not support joins")
    intent = selection.get("intent")
    if intent not in {"lookup", "count", "exists"}:
        raise ValueError("Unsupported intent: " + repr(intent))
    path = _choose_path(concept, selection["question"])
    chain = path["property_chain"]
    if chain[-1] != concept["uri"]:
        raise ValueError("Traversal does not terminate at selected property")
    namespace = "https://example.org/" + concept["domain"] + "/"
    if any(not iri.startswith(namespace) for iri in chain):
        raise ValueError("Cross-domain traversal is not supported")
    # A count of devices concerns entity nodes, not their identifier values.
    # Only apply this rewrite when the selected schema path actually contains
    # the ECAD hasDevice relationship. Other entity counts remain unsupported.
    entity_count = (
        intent == "count"
        and concept["domain"] == "ecad"
        and bool(re.search(r"\\bdevices?\\b", selection["question"], re.I))
        and not bool(re.search(r"\\b(identifier|identifiers|local\\s+ids?|values?)\\b",
                               selection["question"], re.I))
    )
    if entity_count:
        device_iri = "https://example.org/ecad/hasDevice"
        if device_iri not in chain:
            raise ValueError("No grounded ECAD device traversal for entity count")
        chain = chain[:chain.index(device_iri) + 1]
    triples = []
    for i, predicate in enumerate(chain):
        subject = "?root" if i == 0 else "?n" + str(i)
        obj = ("?device" if entity_count else "?value") if i == len(chain) - 1 else "?n" + str(i + 1)
        triples.append("  " + subject + " " + _iri(predicate) + " " + obj + " .")
    body = "\n".join(triples)
    if intent == "count":
        target = "?device" if entity_count else "?value"
        query = "SELECT (COUNT(DISTINCT " + target + ") AS ?count) WHERE {\\n" + body + "\\n}"
    elif intent == "exists":
        query = "ASK WHERE {\n" + body + "\n}"
    else:
        query = "SELECT DISTINCT ?value WHERE {\n" + body + "\n} LIMIT " + str(limit)
    return {"question": selection["question"], "intent": intent,
            "selected_uri": concept["uri"], "chosen_path": chain,
            "count_target": ("device" if entity_count else "value") if intent == "count" else None,
            "sparql": query, "execution_status": "not_executed",
            "cross_domain_join": "not_supported"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path,
                        default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    parser.add_argument("--query", required=True)
    parser.add_argument("--model", default="qwen2.5-coder:3b")
    parser.add_argument("--endpoint", default="http://localhost:11434")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    index = json.loads(args.index.read_text(encoding="utf-8"))
    selection = select_intent(index, args.query, model=args.model, endpoint=args.endpoint)
    print(json.dumps(compile_sparql(selection, args.limit), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
