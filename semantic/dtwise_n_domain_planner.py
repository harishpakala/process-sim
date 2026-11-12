"""Deterministic N-domain join planner over explicitly cataloged SHACL paths.

No graph-search inference: a query's exact domain set must match one declared
join plan. Legacy two/three-domain catalogs are normalized without changing
their approval status. Future plans use n_domain_plans (see module docstring).
"""
from semantic.dtwise_sparql_compiler import _iri

# n_domain_plans entries:
# {"id":"...", "domains":["a","b",...], "status":"verified" or
#  "candidate_pending_semantic_approval", "comparison":"string_equality",
#  "anchors":[{"domain":"a","paths":[[IRI,...]],"entity_var":"?entityA",
#              "identifier_var":"?idA"}, ...]}
# The first anchor's identifier is compared to each other identifier.
# No implicit joins, transitive mapping inference, or ontology guessing.


def _normalize(catalog):
    plans = []
    for m in catalog.get("mappings", []):
        source, target = m["source_domain"], m["target_domain"]
        plans.append({
            "id": m["id"], "domains": [source, target],
            "mapping_ids": [m["id"]], "status": m.get("status"),
            "comparison": m.get("comparison"),
            "anchors": [
                {"domain": source, "paths": [m["source_path"]]},
                {"domain": target, "paths": [m["target_path"]]},
            ],
            "approval_statuses": [m.get("status")],
            "legacy_kind": "two",
        })
    for m in catalog.get("three_domain_mappings", []):
        base_matches = [b for b in catalog.get("mappings", [])
                        if b.get("id") == m.get("base_mapping_id")]
        if len(base_matches) != 1:
            raise ValueError("Three-domain base mapping missing or ambiguous")
        b = base_matches[0]
        plans.append({
            "id": m["id"], "domains": list(m["domains"]),
            "mapping_ids": [b["id"], m["id"]],
            "status": m.get("status"), "comparison": m.get("comparison"),
            "anchors": [
                {"domain": b["source_domain"], "paths": [b["source_path"]]},
                {"domain": b["target_domain"], "paths": [b["target_path"]]},
                {"domain": "dexpi", "paths": m.get("dexpi_paths", [])},
            ],
            "approval_statuses": [b.get("status"), m.get("status")],
            "base_comparison": b.get("comparison"),
            "legacy_kind": "three",
        })
    for m in catalog.get("n_domain_plans", []):
        plans.append({**m, "mapping_ids": [m["id"]],
                      "approval_statuses": [m.get("status")],
                      "legacy_kind": "generic"})
    return plans


def _render_path(path, prefix, entity, identifier, legacy_two=False):
    if len(path) < 2:
        raise ValueError("Identifier traversal must contain an entity edge")
    triples = []
    for i, predicate in enumerate(path):
        subject = ("?" + prefix + "Root" if i == 0 else
                   "?" + prefix + str(i) if legacy_two else
                   entity if i == len(path) - 1 else "?" + prefix + str(i))
        obj = (identifier if i == len(path) - 1 else
               "?" + prefix + str(i + 1) if legacy_two else
               entity if i == len(path) - 2 else "?" + prefix + str(i + 1))
        triples.append("    " + subject + " " + _iri(predicate) + " " + obj + " .")
    return triples


def compile_n_domain(question, index, catalog, mentioned, allow_candidate, limit,
                     validate_path):
    """Compile exactly one explicit plan; validate every complete SHACL path."""
    if not isinstance(limit, int) or not 1 <= limit <= 10000:
        raise ValueError("LIMIT must be between 1 and 10000")
    if len(mentioned) < 2:
        raise ValueError("Cross-domain queries require at least two explicit domains")
    plans = [p for p in _normalize(catalog) if set(p["domains"]) == mentioned]
    if len(plans) != 1:
        raise ValueError("Expected exactly one explicit catalog plan for requested domains")
    plan = plans[0]
    anchors = plan.get("anchors", [])
    if (len(anchors) != len(mentioned) or
            len(set(plan["domains"])) != len(plan["domains"]) or
            {a.get("domain") for a in anchors} != mentioned or
            len({a.get("domain") for a in anchors}) != len(anchors)):
        raise ValueError("Plan anchors must match requested domains exactly")
    statuses = plan["approval_statuses"]
    if any(s != "verified" and not (
            allow_candidate and s == "candidate_pending_semantic_approval")
           for s in statuses):
        raise ValueError("Join mapping is not semantically approved; use --allow-candidate for exploratory execution")
    if plan.get("comparison") != "string_equality" or (
            plan.get("base_comparison", "string_equality") != "string_equality"):
        raise ValueError("Unsupported join comparison")
    if plan["legacy_kind"] == "three":
        if set(plan["domains"]) != {"engineeringbom", "ecad", "dexpi"}:
            raise ValueError("Legacy three-domain mapping has unexpected domains")
    # Use fixed variables for the validated legacy outputs, otherwise generate
    # deterministic variables based on anchor order.
    legacy_two = plan["legacy_kind"] == "two"
    legacy_three = plan["legacy_kind"] == "three"
    reserved = {"?assetId", "?bomRecord", "?device", "?dexpiObject",
                "?ecadId", "?dexpiId", "?ebomId"}
    used = set()
    compiled = []
    for i, anchor in enumerate(anchors):
        domain = anchor["domain"]
        paths = anchor.get("paths", [])
        if not isinstance(paths, list) or not paths or any(
                not isinstance(p, list) or len(p) < 2 for p in paths):
            raise ValueError("Anchor paths missing or invalid")
        if len({tuple(p) for p in paths}) != len(paths):
            raise ValueError("Anchor paths missing or duplicated")
        if len({p[-1] for p in paths}) != 1:
            raise ValueError("Alternative paths must share the same identifier property")
        for path in paths:
            validate_path(index, domain, path)
        if legacy_two:
            prefix = ("eb", "ec")[i]
            identifier = ("?ebomId", "?ecadId")[i]
            entity = "?" + prefix + str(len(paths[0]) - 1)
        elif legacy_three:
            prefix = ("eb", "ec", "dx")[i]
            identifier = ("?assetId", "?ecadId", "?dexpiId")[i]
            entity = ("?bomRecord", "?device", "?dexpiObject")[i]
        else:
            prefix = "d" + str(i)
            identifier = anchor.get("identifier_var", "?id" + str(i))
            entity = anchor.get("entity_var", "?entity" + str(i))
            if (not isinstance(identifier, str) or not isinstance(entity, str) or
                    not identifier.startswith("?") or not entity.startswith("?") or
                    not identifier[1:].isidentifier() or not entity[1:].isidentifier() or
                    identifier == entity or identifier in used or entity in used or
                    identifier in reserved or entity in reserved):
                raise ValueError("Invalid or colliding anchor variables")
        used.update((identifier, entity))
        alternatives = []
        for j, path in enumerate(paths):
            branch_prefix = prefix + str(j) if len(paths) > 1 else prefix
            alternatives.append("\n".join(_render_path(
                path, branch_prefix, entity, identifier, legacy_two=legacy_two)))
        if len(alternatives) == 1:
            body = alternatives[0]
        else:
            body = "\n  UNION\n".join("  {\n" + x + "\n  }" for x in alternatives)
        compiled.append((entity, identifier, body))
    # For generic plans, prevent generated intermediates/root variables from
    # colliding with user-supplied projected variables.
    if not (legacy_two or legacy_three):
        for i, anchor in enumerate(anchors):
            for j, path in enumerate(anchor["paths"]):
                prefix = "d" + str(i) + (str(j) if len(anchor["paths"]) > 1 else "")
                intermediates = {"?" + prefix + "Root"} | {
                    "?" + prefix + str(k) for k in range(1, len(path) - 1)}
                if intermediates & used:
                    raise ValueError("Anchor variables collide with traversal variables")
    first_id = compiled[0][1]
    filters = ["  FILTER(STR(" + first_id + ") = STR(" + identifier + "))"
               for _, identifier, _ in compiled[1:]]
    projection = ([compiled[0][1]] + [x[0] for x in compiled]
                  if legacy_three else
                  [compiled[0][1]] + [x[0] for x in compiled] if legacy_two else
                  [x[0] for x in compiled] + [x[1] for x in compiled])
    sparql = ("SELECT DISTINCT " + " ".join(projection) + " WHERE {\n" +
              "\n".join(x[2] for x in compiled) + "\n" +
              "\n".join(filters) + "\n} LIMIT " + str(limit))
    result = {
        "question": question, "mapping_status": plan["status"],
        "candidate_opt_in": bool(allow_candidate), "sparql": sparql,
        "execution_status": "not_executed",
        "cross_domain_join": ("verified" if all(
            s == "verified" for s in statuses) else "candidate"),
    }
    if legacy_two:
        result["mapping_id"] = plan["id"]
    else:
        result["mapping_ids"] = plan["mapping_ids"]
    return result
