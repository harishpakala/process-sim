"""Opt-in, read-only execution of ontology-derived instance lookup plans."""
import json
import re
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ENTITY_VAR = re.compile(r"^SELECT DISTINCT (\?[A-Za-z][A-Za-z0-9]*) \?identity WHERE \{")


def _endpoint(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Invalid SPARQL endpoint")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Endpoint credentials and fragments are unsupported")
    return url


def _query(endpoint, sparql, timeout=10):
    """POST a SPARQL SELECT query, accepting only SPARQL JSON results."""
    from urllib.parse import urlencode
    request = Request(
        _endpoint(endpoint),
        data=urlencode({"query": sparql}).encode("utf-8"),
        headers={"Accept": "application/sparql-results+json",
                 "Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
        method="POST")
    with urlopen(request, timeout=timeout) as response:
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise ValueError("SPARQL response exceeds size limit")
    data = json.loads(payload.decode("utf-8"))
    bindings = data.get("results", {}).get("bindings")
    if not isinstance(bindings, list):
        raise ValueError("Invalid SPARQL SELECT JSON result")
    return bindings


def resolve_instance_lookups(plans, endpoint, max_plans=40, timeout=10,
                             query_fn=None):
    """Resolve candidate RDF nodes without asserting their semantic role.

    Matching a name/identifier is evidence of a candidate node, not proof
    that the node is the requested engineering entity or linked to a target.
    Errors fail closed. A per-query LIMIT may truncate results.
    """
    if not isinstance(max_plans, int) or not 1 <= max_plans <= 100:
        raise ValueError("Invalid plan count")
    if not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
        raise ValueError("Invalid timeout")
    _endpoint(endpoint)
    runner = query_fn or _query
    matches, errors = {}, []
    for plan in plans[:max_plans]:
        if plan.get("status") != "unexecuted_instance_lookup":
            continue
        sparql = plan.get("sparql", "")
        match = ENTITY_VAR.match(sparql)
        if not match:
            errors.append({"domain": plan.get("domain"), "error": "unsupported_query_shape"})
            continue
        var = match.group(1)[1:]
        try:
            rows = runner(endpoint, sparql, timeout=timeout)
            if not isinstance(rows, list):
                raise ValueError("Invalid result rows")
            for row in rows:
                entity = row.get(var, {})
                identity = row.get("identity", {})
                if (entity.get("type") != "uri" or not isinstance(entity.get("value"), str)
                        or identity.get("type") not in ("literal", "typed-literal")
                        or not isinstance(identity.get("value"), str)):
                    continue
                uri = entity["value"]
                evidence = {"domain": plan.get("domain"),
                            "identity_property": plan.get("identity_property"),
                            "identity_value": identity["value"],
                            "property_chain": plan.get("property_chain")}
                matches.setdefault(uri, []).append(evidence)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append({"domain": plan.get("domain"),
                           "error": type(exc).__name__})
    resolved = [{"uri": uri, "evidence": sorted(items, key=lambda x: (
                 str(x["domain"]), str(x["identity_property"]), str(x["identity_value"])))}
                for uri, items in sorted(matches.items())]
    status = ("execution_incomplete" if errors or len(plans) > max_plans else
              "no_matches" if not resolved else
              "unique_candidate" if len(resolved) == 1 else "ambiguous_candidates")
    return {"status": status, "candidate_instances": resolved,
            "errors": errors, "plans_executed": min(len(plans), max_plans),
            "relationship_verified": False}
