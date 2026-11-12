"""Role-aware relationship evidence discovery, without inferred joins.

Discover structural SHACL paths for each side of a relationship question.
An identifier mapping alone does not establish equipment/instrument association.
"""
import re

from semantic.dtwise_concept_resolver import _tokens, _traversals

RELATION_WORDS = {"associated", "association", "connected", "related",
                  "linked", "correspond", "corresponding"}
STOP = {"which", "what", "the", "a", "an", "are", "is", "with", "to",
        "of", "in", "according", "integrated", "representations",
        "representation", "engineering", "process"}


def is_relationship_question(question):
    if not isinstance(question, str):
        return False
    return bool(set(re.findall(r"[a-z0-9]+", question.casefold())) & RELATION_WORDS)


def _role_terms(text):
    terms = _tokens(text) - STOP - RELATION_WORDS
    # Normalize grammatical variants, not engineering-domain synonyms.
    normalized = set()
    for term in terms:
        normalized.add(term)
        if term.endswith("ies") and len(term) > 4:
            normalized.add(term[:-3] + "y")
        elif term.endswith("s") and len(term) > 3:
            normalized.add(term[:-1])
    return normalized


def _roles(question):
    match = re.search(
        r"\b(?:which|what)\s+(.*?)\s+are\s+"
        r"(?:associated|connected|related|linked)\s+"
        r"(?:with|to)\s+(.*?)(?:\s*,?\s+according\s+to\b|\?|$)",
        question, flags=re.I)
    if not match:
        return {"subject": {"text": None, "terms": []},
                "target": {"text": None, "terms": []},
                "parse_status": "unresolved"}
    target, subject = match.group(1).strip(), match.group(2).strip()
    return {"subject": {"text": subject, "terms": sorted(_role_terms(subject))},
            "target": {"text": target, "terms": sorted(_role_terms(target))},
            "parse_status": "parsed"}


def _matches(term, token):
    if term == token:
        return True
    # instrument/instruments/instrumentation share a lexical stem.
    return (len(term) >= 6 and len(token) >= 6
            and term.startswith("instrument") and token.startswith("instrument"))


def _discover(index, terms):
    evidence = []
    for concept in index.get("concepts", []):
        if concept.get("kind") != "property":
            continue
        uri, domain = concept.get("uri"), concept.get("domain")
        if not isinstance(uri, str) or not isinstance(domain, str):
            continue
        for traversal in _traversals(index, uri, domain):
            if not traversal.get("complete_to_root"):
                continue
            chain = traversal.get("property_chain", [])
            if not chain or chain[-1] != uri:
                continue
            # Match every edge, not only the terminal leaf property.
            path_terms = set()
            for edge in chain:
                path_terms.update(_tokens(re.split(r"[/#]", edge)[-1]))
            matched = sorted(t for t in terms if any(_matches(t, p) for p in path_terms))
            if not matched:
                continue
            evidence.append({"domain": domain, "uri": uri,
                             "matched_terms": matched, "property_chain": chain,
                             "match_scope": "shacl_path"})
    evidence.sort(key=lambda e: (-len(e["matched_terms"]),
                                 len(e["property_chain"]), e["domain"],
                                 e["uri"], e["property_chain"]))
    return evidence[:20]



def _schema_graph(index):
    """Directed SHACL traversal graph; edges are observed predicate transitions.

    Root is a separate node for each domain/start shape. Two sibling properties
    are not a subject-to-target association merely because they share a root.
    """
    graph = {}
    for concept in index.get("concepts", []):
        if concept.get("kind") != "property":
            continue
        uri, domain = concept.get("uri"), concept.get("domain")
        if not isinstance(uri, str) or not isinstance(domain, str):
            continue
        for traversal in _traversals(index, uri, domain):
            if not traversal.get("complete_to_root"):
                continue
            chain = traversal.get("property_chain", [])
            if not chain or chain[-1] != uri:
                continue
            root = (domain, traversal.get("start_shape") or "unknown-root", ())
            for depth, predicate in enumerate(chain):
                parent = (root[0], root[1], tuple(chain[:depth]))
                child = (root[0], root[1], tuple(chain[:depth + 1]))
                graph.setdefault(parent, set()).add((predicate, child))
    return graph


def _schema_connections(index, subject_evidence, target_evidence):
    """Discover only directed ancestor-to-descendant schema connections.

    These are structural candidates, not proof of entity identity, assembly
    membership, or association. No reverse edges or cross-domain equality.
    """
    graph = _schema_graph(index)
    paths = []
    for s in subject_evidence:
        for t in target_evidence:
            if s["domain"] != t["domain"]:
                continue
            left, right = tuple(s["property_chain"]), tuple(t["property_chain"])
            if len(left) >= len(right) or right[:len(left)] != left:
                continue
            suffix = right[len(left):]
            # The suffix must be a directed sequence in the indexed graph.
            found = False
            for node in graph:
                if node[0] != s["domain"] or node[2] != left:
                    continue
                cursor = node
                for edge in suffix:
                    choices = [n for predicate, n in graph.get(cursor, ())
                               if predicate == edge]
                    if len(choices) != 1:
                        break
                    cursor = choices[0]
                else:
                    found = True
                    break
            if found:
                paths.append({"domain": s["domain"],
                              "subject_path": list(left),
                              "target_path": list(right),
                              "connecting_predicates": list(suffix),
                              "status": "structural_candidate_only"})
    return sorted(paths, key=lambda p: (len(p["connecting_predicates"]),
                                        p["domain"], p["subject_path"],
                                        p["target_path"]))[:20]

def plan_relationship(question, index):
    if not is_relationship_question(question):
        raise ValueError("Not a relationship question")
    if not isinstance(index, dict):
        raise ValueError("Relationship planning requires the ontology schema index")
    roles = _roles(question)
    subject = _discover(index, roles["subject"]["terms"])
    target = _discover(index, roles["target"]["terms"])
    connections = _schema_connections(index, subject, target)\n    missing = [role for role, matches in (("subject", subject), ("target", target))
               if not matches]
    return {
        "question": question,
        "intent": "relationship_lookup",
        "status": "requires_relationship_grounding",
        "sparql": None,
        "execution_status": "not_executed",
        "cross_domain_join": "not_planned",
        "reason": ("Missing ontology/SHACL evidence for: " + ", ".join(missing) + ". "
                   if missing else "") +
                  ("No verified subject-to-target association path has been "
                   "established. Shared root paths or identifier equality "
                   "alone do not prove the requested relationship."),
        "schema_connections": connections,\n        "role_plan": roles,
        "role_evidence": {"subject": subject, "target": target},
        # Retain legacy key for consumers of the initial diagnostic response.
        "ontology_evidence": subject + target,
    }
