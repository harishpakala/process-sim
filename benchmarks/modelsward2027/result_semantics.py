"""Shared candidate result contract. No execution or semantic-equivalence claims."""
from collections import Counter
import json

def term(value):
    if value is None:
        return ("unbound",)
    kind = value["type"]
    if kind == "uri":
        return ("uri", value["value"])
    if kind in ("literal", "typed-literal"):
        lang = value.get("xml:lang", value.get("lang", "")).lower()
        datatype = value.get("datatype") or ("http://www.w3.org/1999/02/22-rdf-syntax-ns#langString" if lang else "http://www.w3.org/2001/XMLSchema#string")
        return ("literal", value["value"], datatype, lang)
    raise ValueError("Unsupported RDF term type: "+kind)

def rows(result, role_to_variable, roles):
    if set(role_to_variable) != set(roles) or len(set(role_to_variable.values())) != len(roles):
        raise ValueError("Explicit one-to-one projection alignment required")
    variables = result["head"]["vars"]
    if len(variables) != len(roles) or set(variables) != set(role_to_variable.values()):
        raise ValueError("Projection arity or alignment mismatch")
    return [tuple(term(row.get(role_to_variable[role])) for role in roles)
            for row in result["results"]["bindings"]]

def compare(actual, expected, contract, actual_alignment, expected_alignment):
    mode = contract["mode"]
    if mode not in ("set", "bag"):
        raise ValueError("Ordered and negative contracts require separate evaluation")
    roles = contract["roles"]
    a = rows(actual, actual_alignment, roles)
    e = rows(expected, expected_alignment, roles)
    return {"contract_match": set(a)==set(e) if mode=="set" else Counter(a)==Counter(e),
            "set_match":set(a)==set(e), "bag_match":Counter(a)==Counter(e),
            "actual_rows":len(a),"expected_rows":len(e),
            "actual_duplicate_rows":len(a)-len(set(a)),
            "expected_duplicate_rows":len(e)-len(set(e)),
            "structural_review_required":True}
