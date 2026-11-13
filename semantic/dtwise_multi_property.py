"""Deterministic multi-property SPARQL on a single SHACL-grounded entity path.

No instance inspection, inferred joins, or model-generated predicates.
"""
import json
import re

from semantic.dtwise_concept_resolver import _tokens


def compile_multi_property(selection, limit=100):
    from semantic.dtwise_sparql_compiler import _iri

    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError("LIMIT must be between 1 and 10000")
    if selection.get("join_status") != "unverified":
        raise ValueError("Cross-domain joins require explicit mapping")
    if selection.get("intent") != "lookup":
        raise ValueError("Multi-property compilation currently supports lookup only")
    concepts = selection.get("selected_concepts", [])
    if not isinstance(concepts, list) or not 2 <= len(concepts) <= 4:
        raise ValueError("Multi-property lookup requires two to four properties")
    if any(c.get("kind") != "property" for c in concepts):
        raise ValueError("Only property concepts are supported")
    domains = {c.get("domain") for c in concepts}
    if len(domains) != 1:
        raise ValueError("Cross-domain joins require explicit mapping")
    domain = next(iter(domains))
    if not isinstance(domain, str) or not domain:
        raise ValueError("Invalid domain")
    namespace = "https://example.org/" + domain + "/"
    uris = [c.get("uri") for c in concepts]
    if len(set(uris)) != len(uris):
        raise ValueError("Duplicate selected properties")

    # A path is only eligible if it is complete, ends at the selected
    # predicate, and has at least one entity edge preceding that predicate.
    choices = []
    for concept in concepts:
        valid = []
        for path in concept.get("paths", []):
            chain = path.get("property_chain", [])
            if (path.get("complete_to_root") and len(chain) >= 3
                    and chain[-1] == concept["uri"]
                    and all(isinstance(p, str) and p.startswith(namespace)
                            for p in chain)):
                valid.append(tuple(chain))
        if not valid:
            raise ValueError("No complete grounded entity path for " + str(concept["uri"]))
        choices.append(set(valid))

    # Only identical root-to-entity predicate chains can be combined.
    shared = set(tuple(p[:-1]) for p in choices[0])
    for paths in choices[1:]:
        shared &= {tuple(p[:-1]) for p in paths}
    if len(shared) != 1:
        raise ValueError("Ambiguous or missing common SHACL entity path")
    prefix = next(iter(shared))
    selected_paths = []
    for uri, paths in zip(uris, choices):
        chain = prefix + (uri,)
        if chain not in paths:
            raise ValueError("No common grounded property traversal")
        selected_paths.append(list(chain))

    triples = []
    for i, predicate in enumerate(prefix):
        subj = "?root" if i == 0 else "?n" + str(i)
        obj = "?entity" if i == len(prefix) - 1 else "?n" + str(i + 1)
        triples.append("  " + subj + " " + _iri(predicate) + " " + obj + " .")
    for i, uri in enumerate(uris):
        triples.append("  ?entity " + _iri(uri) + " ?value" + str(i + 1) + " .")

    constraints = selection.get("value_constraints", [])
    if not isinstance(constraints, list) or len(constraints) > 1:
        raise ValueError("Only one grounded equality constraint is supported")
    filter_metadata = None
    if constraints:
        c = constraints[0]
        if not isinstance(c, dict):
            raise ValueError("Invalid value constraint")
        text, role = c.get("text"), c.get("role")
        if not isinstance(text, str) or not text.strip() or not isinstance(role, str):
            raise ValueError("Invalid value constraint fields")
        if text.casefold() not in selection.get("question", "").casefold():
            raise ValueError("Value constraint not present in original question")
        matching = [i for i, uri in enumerate(uris)
                    if _tokens(role) == _tokens(re.split(r"[/#]", uri)[-1])]
        if len(matching) != 1:
            raise ValueError("Filter role must uniquely match a selected property")
        i = matching[0]
        triples.append("  FILTER(STR(?value" + str(i + 1) + ") = "
                       + json.dumps(text, ensure_ascii=True) + ")")
        filter_metadata = {"property": uris[i], "operator": "exact_string", "text": text}

    projection = " ".join(["?entity"] + ["?value" + str(i + 1)
                                         for i in range(len(uris))])
    query = ("SELECT DISTINCT " + projection + " WHERE {\n"
             + "\n".join(triples) + "\n} LIMIT " + str(limit))
    return {"question": selection["question"], "intent": "lookup",
            "selected_uris": uris, "chosen_paths": selected_paths,
            "common_entity_path": list(prefix), "value_filter": filter_metadata,
            "sparql": query, "execution_status": "not_executed",
            "cross_domain_join": "not_supported"}
