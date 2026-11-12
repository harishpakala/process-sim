"""Compile DTWise semantic selections and explicitly cataloged cross-domain joins.

Run: python -m semantic.dtwise_sparql_compiler --query "ECAD device local identifier"
Cross-domain joins require an explicit catalog mapping and semantic approval or opt-in.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from semantic.dtwise_concept_resolver import _tokens, _traversals, _mentioned_domains
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


def _entity_count_path(index, question, domain, selected_chain):
    """Find an entity edge from indexed SHACL paths, never from a guessed IRI.

    Return None for explicit value counts. Raise for unresolved entity counts.
    """
    if index is None:
        raise ValueError("Entity counting requires the schema index")
    words = re.findall(r"[a-z0-9]+", question.lower())
    if any(w in {"identifier", "identifiers", "id", "ids", "value", "values"}
           for w in words):
        return None
    # Treat the last non-domain noun in a count request as the entity target.
    stop = {"count", "number", "of", "how", "many", "the", "a", "an",
            "are", "there", "in", "all", "total", "distinct", "unique"}
    domain_words = set()
    for alias in _mentioned_domains(question):
        domain_words.update(_tokens(alias))
    nouns = [w for w in words if w not in stop and w not in domain_words]
    if not nouns:
        raise ValueError("Entity count target is not explicit")
    noun = nouns[-1]
    singular = noun[:-3] + "y" if noun.endswith("ies") else (
        noun[:-1] if noun.endswith("s") and not noun.endswith("ss") else noun)
    candidates = []
    for c in index.get("concepts", []):
        if c.get("domain") != domain or c.get("kind") != "property":
            continue
        uri = c["uri"]
        local = re.split(r"[/#]", uri)[-1]
        # The terminal predicate must name an individual, not a collection.
        # hasDevice matches device; hasDevices does not.
        local_words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", local)
        if not local_words:
            continue
        parts = [word.lower() for word in local_words]
        # Exact entity edges (hasDevice), or a documented record edge
        # (hasBOMItemRecord) for an item request. Never count collections.
        exact = parts[-1] == singular
        record = (parts[-1] == "record" and singular in parts[:-1])
        if not (exact or record):
            continue
        for path in _traversals(index, uri, domain):
            chain = path["property_chain"]
            if not path["complete_to_root"] or chain[-1] != uri:
                continue
            if not all(x.startswith("https://example.org/" + domain + "/") for x in chain):
                continue
            # Preserve the known root path whenever the selector chose a collection.
            if selected_chain and chain[0] != selected_chain[0]:
                continue
            candidates.append(chain)
    if not candidates:
        raise ValueError("No grounded entity path for target: " + noun)
    candidates.sort(key=lambda p: (len(p), p))
    shortest = len(candidates[0])
    best = {tuple(p) for p in candidates if len(p) == shortest}
    if len(best) != 1:
        raise ValueError("Ambiguous entity traversal for target: " + noun)
    return list(next(iter(best)))


def _grounded_value_filter(selection, concept):
    """Compile only an exact value on the selected terminal ontology property.

    No predicate is inferred from a model-supplied role. Other roles, multiple
    constraints, and values absent from the question fail closed.
    """
    constraints = selection.get("value_constraints", [])
    if not constraints:
        return None
    if not isinstance(constraints, list) or len(constraints) != 1:
        raise ValueError("Value constraints require exactly one grounded equality")
    constraint = constraints[0]
    if not isinstance(constraint, dict):
        raise ValueError("Value constraints must be objects")
    value, role = constraint.get("text"), constraint.get("role")
    if not isinstance(value, str) or not value.strip() or not isinstance(role, str):
        raise ValueError("Value constraints require nonempty text and role")
    question = selection.get("question", "")
    if value.casefold() not in question.casefold():
        raise ValueError("Value constraint not present in original question")
    # A role may only refer to the property that is already selected.
    # Require an exact match to the ontology local name or its tokenized form.
    local = re.split(r"[/#]", concept["uri"])[-1]
    if _tokens(role) != _tokens(local):
        raise ValueError("Value constraint role does not match selected property")
    # JSON string quoting is compatible with SPARQL quoted string escapes.
    return "  FILTER(STR(?value) = " + json.dumps(value, ensure_ascii=True) + ")"


def compile_sparql(selection, limit=100, index=None):
    if not isinstance(limit, int) or not 1 <= limit <= 10000:
        raise ValueError("LIMIT must be between 1 and 10000")
    selected = selection.get("selected_concepts", [])
    if len(selected) > 1:
        from semantic.dtwise_multi_property import compile_multi_property
        return compile_multi_property(selection, limit=limit)
    if len(selected) != 1:
        raise ValueError("Single-property compilation requires exactly one selected concept")
    concept = selected[0]
    if concept.get("kind") != "property":
        raise ValueError("Only property concepts are supported")
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
    entity_count = False
    if intent == "count":
        planned = _entity_count_path(index, selection["question"], concept["domain"], chain)
        if planned is not None:
            chain = planned
            entity_count = True
    triples = []
    for i, predicate in enumerate(chain):
        subject = "?root" if i == 0 else "?n" + str(i)
        obj = ("?entity" if entity_count else "?value") if i == len(chain) - 1 else "?n" + str(i + 1)
        triples.append("  " + subject + " " + _iri(predicate) + " " + obj + " .")
    value_filter = _grounded_value_filter(selection, concept)
    if value_filter and entity_count:
        raise ValueError("Entity counts with value constraints require a grounded entity filter plan")
    if value_filter:
        triples.append(value_filter)
    body = "\n".join(triples)
    if intent == "count":
        target = "?entity" if entity_count else "?value"
        query = "SELECT (COUNT(DISTINCT " + target + ") AS ?count) WHERE {\n" + body + "\n}"
    elif intent == "exists":
        query = "ASK WHERE {\n" + body + "\n}"
    else:
        query = "SELECT DISTINCT ?value WHERE {\n" + body + "\n} LIMIT " + str(limit)
    return {"question": selection["question"], "intent": intent,
            "selected_uri": concept["uri"], "chosen_path": chain,
            "value_filter": {"property": concept["uri"], "operator": "exact_string",
                             "text": selection["value_constraints"][0]["text"]}
                            if value_filter else None,
            "count_target": ("entity" if entity_count else "value") if intent == "count" else None,
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
    parser.add_argument("--allow-candidate", action="store_true",
                        help="Allow explicitly cataloged, unapproved cross-domain mappings")
    parser.add_argument("--catalog", type=Path,
                        default=Path(__file__).parent / "ontology" / "dtwise" / "cross-domain-mappings.json")
    args = parser.parse_args()
    index = json.loads(args.index.read_text(encoding="utf-8"))
    mentioned = {domain.lower() for domain in _mentioned_domains(args.query)}
    if len(mentioned) > 1:
        from semantic.dtwise_cross_domain import compile_cross_domain
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        result = compile_cross_domain(args.query, index, catalog,
                                      allow_candidate=args.allow_candidate, limit=args.limit)
    else:
        selection = select_intent(index, args.query, model=args.model, endpoint=args.endpoint)
        result = compile_sparql(selection, args.limit, index=index)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
