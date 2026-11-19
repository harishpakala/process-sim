"""Phase 5.5: schema-derived structural validation for sibling join intents.

This validates graph structure and filter attachment, NOT natural-language
entailment. Do not compile or execute a model proposal on this check alone.
"""
from process_sim.dtwise.experimental_shacl_join_topology import verified_shared_ancestor
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError


def validate_schema_join_intent(intent, qualified):
    """Validate two sibling projections and zero or more ancestor equality filters.

    The candidate registry must already have been qualified against the index.
    This intentionally does not infer whether the user requested these paths.
    """
    if not isinstance(intent, dict) or set(intent) != {
        "domain", "operation", "result_property_ids", "join",
        "boolean_operator", "filters",
    }:
        raise SelectionContractError("Invalid schema intent fields")
    domain = qualified["prompt"]["domain"]
    if intent["domain"] != domain or intent["operation"] != "select":
        raise SelectionContractError("Invalid schema intent domain or operation")
    ids = intent["result_property_ids"]
    topology = verified_shared_ancestor(qualified, ids)
    join = intent["join"]
    if not isinstance(join, dict) or set(join) != {"kind", "owner"} or join["kind"] != "shared_ancestor":
        raise SelectionContractError("Invalid schema intent join")
    owner = join["owner"]
    if not isinstance(owner, str) or not owner.strip():
        raise SelectionContractError("Invalid join owner")
    # The supplied owner is a human-readable label; the URI is authoritative.
    paths = {c["id"]: c for c in qualified["prompt"]["candidates"]
             if c["kind"] == "property"}
    ancestor_uri = topology["ancestor_uri"]
    owner_names = {c["path"].split(" → ")[-2] for c in paths.values()
                   if c["id"] in ids and len(c["path"].split(" → ")) >= 2}
    # Owner can be the URI itself; labels are allowed only when explicitly
    # represented by the shared prefix of both verified candidate paths.
    ancestor_depth = len(topology["shared_node_uris"]) - 1
    shared_labels = []
    for rid in ids:
        parts = paths[rid]["path"].split(" → ")
        if len(parts) <= ancestor_depth:
            raise SelectionContractError("Invalid ancestor path label")
        shared_labels.append(parts[ancestor_depth])
    if owner != ancestor_uri and not (shared_labels[0] == shared_labels[1] == owner):
        raise SelectionContractError("Join owner does not match verified ancestor")
    filters = intent["filters"]
    if not isinstance(filters, list) or intent["boolean_operator"] != "and":
        raise SelectionContractError("Unsupported filter combination")
    registry = qualified["registry"]
    seen = set()
    for f in filters:
        if not isinstance(f, dict) or set(f) != {
            "property_id", "owner", "property", "operator", "value",
        }:
            raise SelectionContractError("Invalid schema filter fields")
        fid = f["property_id"]
        if not isinstance(fid, str) or fid in seen or fid not in paths:
            raise SelectionContractError("Unknown or duplicate filter candidate")
        seen.add(fid)
        entry = registry[fid]
        if (entry["domain"] != domain or entry["kind"] != "property" or
                entry["node_uris"] != topology["shared_node_uris"] or
                entry["edges"] != topology["shared_edges"] or
                entry["property"]["owner"] != ancestor_uri):
            raise SelectionContractError("Filter does not attach to shared ancestor")
        if (f["owner"] != owner or f["property"] != paths[fid]["property_name"] or
                f["operator"] != "=" or not isinstance(f["value"], str)):
            raise SelectionContractError("Invalid filter semantics")
    return intent
