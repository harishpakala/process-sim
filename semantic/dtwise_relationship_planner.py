"""Relationship-question gate and evidence-only planning diagnostics.

A relationship lookup cannot be reduced to a terminal-property lookup.
This module intentionally does not guess an association or a cross-domain join.
"""
import re

from semantic.dtwise_concept_resolver import _tokens, _traversals


def is_relationship_question(question):
    if not isinstance(question, str):
        return False
    words = set(re.findall(r"[a-z0-9]+", question.casefold()))
    return bool(words & {"associated", "association", "connected", "related",
                         "linked", "correspond", "corresponding"})


def plan_relationship(question, index):
    if not is_relationship_question(question):
        raise ValueError("Not a relationship question")
    if not isinstance(index, dict):
        raise ValueError("Relationship planning requires the ontology schema index")

    words = _tokens(question)
    # Evidence is only the ontology's actual property names and SHACL traversals.
    # No hardcoded TEP/ECAD/DEXPI predicates or instance-value guesses.
    evidence = []
    for concept in index.get("concepts", []):
        if concept.get("kind") != "property":
            continue
        uri, domain = concept.get("uri"), concept.get("domain")
        if not isinstance(uri, str) or not isinstance(domain, str):
            continue
        paths = [p["property_chain"] for p in _traversals(index, uri, domain)
                 if p.get("complete_to_root")]
        if not paths:
            continue
        local = re.split(r"[/#]", uri)[-1]
        matched = sorted(_tokens(local) & words)
        if matched:
            evidence.append({"domain": domain, "uri": uri,
                             "matched_terms": matched, "paths": paths})
    evidence.sort(key=lambda item: (-len(item["matched_terms"]),
                                    item["domain"], item["uri"]))
    return {
        "question": question,
        "intent": "relationship_lookup",
        "status": "requires_relationship_grounding",
        "sparql": None,
        "execution_status": "not_executed",
        "cross_domain_join": "not_planned",
        "reason": ("No verified subject-to-target association path has been "
                   "established. Terminal property lookup is not a substitute "
                   "for a relationship query."),
        "ontology_evidence": evidence[:20],
    }
