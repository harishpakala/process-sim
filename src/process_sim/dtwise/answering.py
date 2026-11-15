"""Conservative SHACL-grounded SELECT answering for ECAD and DEXPI.

No LLM-authored SPARQL. Every traversed predicate must come from a validated
SHACL path whose evidence is present in the local schema index.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

LABEL = "http://www.w3.org/2000/01/rdf-schema#label"

# These are *question intent descriptors*, not SPARQL templates. The actual
# predicates are taken from the retrieved, validated SHACL paths.
SUPPORTED_TARGETS = {
    "ecad": {"singular": "device", "plural": "devices"},
    "dexpi": {"singular": "equipment", "plural": "equipment"},
}
LIST_VERBS = {"list", "show", "find", "which", "what", "retrieve", "get"}


def _words(question):
    return set(re.findall(r"[a-z0-9]+", question.lower()))


def _local_name(uri):
    return re.split(r"[/#]", uri.rstrip("/#"))[-1].lower()


def _iri(uri):
    if not isinstance(uri, str) or not re.fullmatch(r"https?://[^\s<>\"{}|\\^`]+", uri):
        raise ValueError("Unsafe or invalid predicate IRI")
    return f"<{uri}>"


def _path_is_grounded(path, schema):
    if path.get("path_valid") is not True or path.get("path_type") != "node_traversal":
        return False
    hops = path.get("hops") or []
    predicates = path.get("properties") or []
    if not hops or len(hops) != len(predicates) or not path.get("end_shape"):
        return False
    if not all(h.get("property") == p and h.get("to_shape") for h, p in zip(hops, predicates)):
        return False
    for previous, following in zip(hops, hops[1:]):
        if previous.get("to_shape") != following.get("from_shape"):
            return False
    if hops[0].get("from_shape") != path.get("start_shape"):
        return False
    if hops[-1].get("to_shape") != path.get("end_shape"):
        return False
    relationship_index = getattr(schema, "relationship_by_id", {})
    evidence = path.get("evidence_ids") or []
    if not evidence or not all(eid in relationship_index for eid in evidence):
        return False
    if not all(h.get("evidence_ids") and all(e in relationship_index for e in h["evidence_ids"]) for h in hops):
        return False
    return True


def plan_entities(question, paths, schema):
    words = _words(question)
    if not words.intersection(LIST_VERBS):
        raise ValueError("Unsupported intent: only entity listing is supported")
    requested = [domain for domain, spec in SUPPORTED_TARGETS.items()
                 if domain in words and words.intersection({spec["singular"], spec["plural"]})]
    if len(requested) != 1:
        raise ValueError("Unsupported or ambiguous domain/entity request")
    domain = requested[0]
    target = SUPPORTED_TARGETS[domain]["singular"]

    candidates = []
    for path in paths:
        if str(path.get("domain", "")).lower() != domain or not _path_is_grounded(path, schema):
            continue
        predicates = path["properties"]
        # Match the *individual entity* at the last hop. Reject collection nodes
        # (e.g. hasEquipments, hasDevices) and terminal identifier properties.
        if _local_name(predicates[-1]) != "has" + target:
            continue
        if len(predicates) < 2:
            # A one-hop path could start from an unbound collection; require a
            # domain-rooted path for this first supported listing scenario.
            continue
        if _local_name(predicates[0]) != "has" + SUPPORTED_TARGETS[domain]["plural"]:
            continue
        candidates.append(path)
    if not candidates:
        raise ValueError(f"No verified {domain.upper()} path to individual {target} instances")
    # Prefer a complete domain-rooted path; score only breaks ties.
    path = max(candidates, key=lambda p: (bool(p.get("path_complete")),
                                           float(p.get("relevance_score") or 0)))
    return {
        "query_type": "SELECT", "intent": "list", "domain": domain,
        "target_variable": target, "source_binding": None,
        "predicates": list(path["properties"]),
        "start_shape": path["start_shape"], "end_shape": path["end_shape"],
        "evidence_ids": list(path["evidence_ids"]),
        "validation_scope": "SHACL structural path (not instance data)",
    }


def plan_ecad_devices(question, paths, schema):
    """Backward-compatible entry point, now supporting DEXPI too."""
    return plan_entities(question, paths, schema)


def compile_sparql(plan, limit=100):
    if plan.get("query_type") != "SELECT" or plan.get("intent") != "list":
        raise ValueError("Only SELECT entity-list plans are supported")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise ValueError("Result limit must be 1..1000")
    domain = plan.get("domain")
    if domain not in SUPPORTED_TARGETS:
        raise ValueError("Unsupported domain")
    target = SUPPORTED_TARGETS[domain]["singular"]
    predicates = plan.get("predicates") or []
    if (plan.get("target_variable") != target or len(predicates) < 2
            or _local_name(predicates[0]) != "has" + SUPPORTED_TARGETS[domain]["plural"]
            or _local_name(predicates[-1]) != "has" + target
            or not plan.get("evidence_ids") or not plan.get("start_shape") or not plan.get("end_shape")):
        raise ValueError("Invalid or ungrounded entity-list plan")
    if any(not p.startswith(f"https://example.org/{domain}/") for p in predicates):
        raise ValueError("Predicate outside selected domain namespace")
    variables = [f"?source", *[f"?node{i}" for i in range(1, len(predicates))], f"?{target}"]
    triples = [f"  {variables[i]} {_iri(p)} {variables[i+1]} ."
               for i, p in enumerate(predicates)]
    return (f"SELECT DISTINCT ?{target} ?label\nWHERE {{\n"
            + "\n".join(triples)
            + f"\n  OPTIONAL {{ ?{target} <{LABEL}> ?label . }}\n}}\n"
            + f"ORDER BY ?{target} ?label\nLIMIT {limit}")


def execute_select(endpoint, sparql, timeout=30):
    parsed = urlparse(endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Endpoint must be a valid HTTP(S) URL without embedded credentials")
    # Do not accept arbitrary user-authored SPARQL: the caller should supply the
    # output of compile_sparql. This check provides defense in depth.
    if not re.match(r"^\s*SELECT\s+DISTINCT\b", sparql, re.IGNORECASE):
        raise ValueError("Only SELECT DISTINCT queries are supported")
    if re.search(r"\b(INSERT|DELETE|DROP|CLEAR|LOAD|CREATE|MOVE|COPY|ADD|SERVICE)\b", sparql, re.I):
        raise ValueError("Forbidden SPARQL keyword")
    response = requests.post(endpoint, data={"query": sparql},
                             headers={"Accept": "application/sparql-results+json"},
                             timeout=timeout)
    response.raise_for_status()
    data = response.json()
    bindings = data.get("results", {}).get("bindings")
    if not isinstance(bindings, list):
        raise ValueError("Endpoint did not return SPARQL SELECT JSON bindings")
    return [{key: value.get("value") for key, value in row.items()}
            for row in bindings]


def build_answer(bindings, target_variable="device"):
    if target_variable not in {"device", "equipment"}:
        raise ValueError("Unsupported answer target")
    entities = {}
    for row in bindings:
        uri = row.get(target_variable)
        if uri:
            entity = entities.setdefault(uri, {"uri": uri, "label": None})
            if row.get("label") and entity["label"] is None:
                entity["label"] = row["label"]
    rows = sorted(entities.values(), key=lambda r: (r["label"] or "", r["uri"]))
    result = {"count": len(rows), "entities": rows,
              "entity_type": target_variable,
              "note": "Count is within the query LIMIT, not necessarily the repository total."}
    # Preserve the original ECAD answer format for existing consumers.
    if target_variable == "device":
        result["devices"] = rows
    return result
