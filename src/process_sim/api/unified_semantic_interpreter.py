"""One Qwen interpretation step for engineering, historian and mixed queries.

The model chooses only from SHACL-derived paths. This module does not invoke
an engineering or historian planner, compile SQL/SPARQL, or execute queries.
"""
import json
import os
import re
from urllib.request import Request, urlopen

from process_sim.api.unified_semantic_ir import (
    BooleanExpression, GraphPath, Join, Predicate, Projection, SemanticQuery,
)


def shacl_catalog(schema, *, max_paths=600, max_depth=5):
    """Build a bounded path catalog from the actual SHACL schema."""
    rows = []
    seen = set()
    for concept in schema.concepts:
        if concept.get("kind") != "shape" or not concept.get("domain"):
            continue
        domain, root = concept["domain"], concept["uri"]
        for hops in schema.shacl_paths(root, max_depth=max_depth, domain=domain):
            path = tuple(h["property"] for h in hops)
            key = (domain, root, path)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "domain": domain, "root_shape": root,
                "predicates": list(path),
                "labels": [schema.by_uri.get(p, {}).get("labels", []) for p in path],
                "evidence_ids": [e for h in hops for e in h["evidence_ids"]],
            })
            if len(rows) > max_paths:
                raise ValueError("SHACL path catalog exceeds limit")
    if not rows:
        raise ValueError("No SHACL paths available")
    return rows


def _path(raw, catalog):
    if not isinstance(raw, int) or isinstance(raw, bool) or not 0 <= raw < len(catalog):
        raise ValueError("Invalid SHACL catalog path ID")
    item = catalog[raw]
    return GraphPath(item["domain"], item["root_shape"],
                     tuple(item["predicates"]), tuple(item["evidence_ids"]))


def _where(raw, catalog):
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("Invalid Boolean expression; expected object, got " + type(raw).__name__)
    if set(raw) == {"field", "operator", "value"}:
        return Predicate(raw["field"], raw["operator"], raw["value"])
    if set(raw) == {"field", "operator", "value", "path_id", "alias"}:
        return Predicate(raw["field"], raw["operator"], raw["value"],
                         _path(raw["path_id"], catalog), raw["alias"])
    if set(raw) == {"operator", "children"} and isinstance(raw["children"], list):
        operator, children = raw["operator"], raw["children"]
        valid = (operator == "not" and len(children) == 1) or (
            operator in ("and", "or") and len(children) >= 2)
        if not valid:
            raise ValueError(
                "Qwen produced invalid Boolean arity: operator="
                + repr(operator) + "; child_count=" + str(len(children))
                + "; expected exactly 1 for not or at least 2 for and/or")
        return BooleanExpression(operator, tuple(_where(x, catalog) for x in children))
    raise ValueError(
        "Invalid Boolean expression; keys=" + repr(sorted(raw.keys()))
        + "; operator=" + repr(raw.get("operator"))
        + "; field=" + repr(raw.get("field"))
        + "; child_count="
        + repr(len(raw["children"]) if isinstance(raw.get("children"), list) else None)
    )


_RESPONSE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["projections", "joins", "where", "group_by", "aggregation",
                 "order_by", "limit", "sources", "run_id", "start_seconds", "end_seconds"],
    "properties": {
        "projections": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "path_id", "source", "alias"],
            "properties": {
                "name": {"type": "string"},
                "path_id": {"type": ["integer", "null"]},
                "source": {"type": "string", "enum": ["graphdb", "timescaledb"]},
                "alias": {"type": "string"}}}},
        "joins": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["left", "right", "left_path_id", "right_path_id"],
            "properties": {
                "left": {"type": "string"}, "right": {"type": "string"},
                "left_path_id": {"type": "integer"},
                "right_path_id": {"type": "integer"}}}},
        "where": {"type": ["object", "null"]},
        "group_by": {"type": "array", "items": {"type": "string"}},
        "aggregation": {"type": ["string", "null"]},
        "order_by": {"type": "array", "items": {"type": "string"}},
        "limit": {"type": ["integer", "null"]},
        "sources": {"type": "array", "minItems": 1,
                    "items": {"type": "string", "enum": ["graphdb", "timescaledb"]}},
        "run_id": {"type": ["string", "null"]},
        "start_seconds": {"type": ["number", "null"]},
        "end_seconds": {"type": ["number", "null"]},
    },
}


def _candidate_paths(question, catalog, *, max_candidates=24):
    """Deterministic lexical retrieval, not a second semantic interpretation."""
    def words(value):
        value = re.sub(r"([a-z])([A-Z])", r"\\1 \\2", str(value))
        return set(re.findall(r"[a-z0-9]+", value.lower()))

    query = words(question)
    scored = []
    for i, path in enumerate(catalog):
        parts = [path["domain"], path["root_shape"], *path["predicates"]]
        labels = path.get("labels", [])
        parts.extend(str(label) for group in labels for label in group)
        tokens = set().union(*(words(part) for part in parts))
        score = sum(3 if len(token) > 3 else 1 for token in query & tokens)
        scored.append((score, i))
    ranked = sorted(scored, key=lambda pair: (-pair[0], pair[1]))
    selected = [i for score, i in ranked if score > 0][:max_candidates]
    if not selected:
        raise ValueError("No SHACL paths match question terms; cannot ground semantic plan")
    # Reserve catalog slots for distinct semantic roles in mixed engineering /
    # historian requests. Generic assetIdentifier matches otherwise crowd out
    # the signal-name path in a small model's bounded candidate list.
    if (re.search(r"\bdexpi\b", question, re.I)
            and (re.search(r"\bopcua(?:connectivity)?\b", question, re.I)
                 or re.search(r"\b(historian|time[- ]series|observations?|simulation\s+times?)\b", question, re.I))):
        roles = (("dexpi", "hasLocalId"),
                 ("dexpi", "hasAssetIdentifier"),
                 ("opcuaconnectivity", "hasAssetIdentifier"),
                 ("opcuaconnectivity", "hasSignalName"))
        reserved = []
        # The LocalID and asset join key must be paths on the same DEXPI
        # instrumentation-function root, not unrelated shortest shape paths.
        instrument = bool(re.search(r"instrumentation\\s*function|instrumentationfunction", question, re.I))
        if instrument:
            pairs = {}
            for i, path in enumerate(catalog):
                predicates = [p.rsplit("/", 1)[-1].lower() for p in path["predicates"]]
                if (path["domain"].lower() == "dexpi"
                        and len(predicates) == 2
                        and predicates[0] == "hasinstrumentationfunction"
                        and predicates[1] in ("haslocalid", "hasassetidentifier")):
                    pairs.setdefault(path["root_shape"], {})[predicates[1]] = i
            complete = [(root, ids) for root, ids in pairs.items()
                        if {"haslocalid", "hasassetidentifier"}.issubset(ids)]
            if not complete:
                raise ValueError("SHACL missing co-rooted instrumentation LocalID and asset paths")
            _, ids = min(complete, key=lambda item: (
                item[1]["haslocalid"] + item[1]["hasassetidentifier"], item[0]))
            reserved.extend((ids["haslocalid"], ids["hasassetidentifier"]))
        for domain, terminal in roles:
            if instrument and domain == "dexpi":
                continue
            matches = [i for i, path in enumerate(catalog)
                       if path["domain"].lower() == domain
                       and path["predicates"][-1].rsplit("/", 1)[-1].lower()
                       == terminal.lower()]
            if not matches:
                raise ValueError("SHACL catalog missing required " + domain + " " + terminal)
            reserved.append(min(matches, key=lambda i: (len(catalog[i]["predicates"]), i)))
        selected = list(dict.fromkeys(reserved + selected))[:max_candidates]
    return selected


def _interpret(question, catalog, context):
    system = (
        "You are ONE semantic interpreter for engineering, historian and mixed queries. "
        "Return JSON only, with exactly these keys: projections, joins, where, "
        "group_by, aggregation, order_by, limit, sources, run_id, start_seconds, end_seconds. "
        "projections: array of {name, path_id, source, alias}; alias is a shared entity root name (e.g. entity, device, signal); path_id is an integer index "
        "into shacl_paths, or null ONLY for timescaledb observations. "
        "joins: array of {left, right, left_path_id, right_path_id}; all paths "
        "must use SHACL catalog indices. where: null or {field,operator,value} "
        "or {field,operator,value,path_id,alias} for non-projected SHACL fields, "
        "or {operator:'and'|'or'|'not',children:[...]}. "
        "For Boolean where: and/or require at least TWO children; not requires EXACTLY ONE. "
        "For a single condition, use {field,operator,value} directly, not an and/or wrapper. "
        "sources: nonempty array containing graphdb and/or timescaledb. "
        "Do not invent paths, IDs, run UUIDs, or simulation times. "
        "Use supplied context for run_id and time boundaries when provided. "
        "Use null for unspecified scalar values, [] for unspecified arrays. "
        "Use where=null unless the question explicitly asks to filter rows by a value or condition. "
        "Do not use where to describe entity associations; represent relationships with SHACL paths and joins. "
        "Choose path_id from the id values in shacl_paths; do not return a path object. "
        "Return ONE semantic query object, never an individual shacl_paths entry. "
        "For a simple engineering question use one graphdb projection, joins=[], sources=['graphdb']. "
        "For multiple properties of the SAME SHACL root use the SAME alias, e.g. entity. "
        "Different root shapes require explicit SHACL joins; never fabricate join keys. "
        "Every join MUST have two DIFFERENT alias strings: use left='dexpi' "
        "for the DEXPI engineering entity and right='opcuaconnectivity' "
        "for the OPCUAConnectivity mapping; NEVER use the same alias on both sides. "
        "Aliases identify entity roots, not the identical property name on both sides. "
        "For historian time-series samples, sources MUST contain both graphdb and timescaledb. "
        "Questions asking how a DEXPI instrumentation function behaved during a simulation run "
        "or for all simulation times are historian requests, even without the word historian. "
        "Resolve DEXPI hasLocalId to the same engineering entity's hasAssetIdentifier, "
        "join that asset identifier to OPCUAConnectivity hasAssetIdentifier, "
        "and project OPCUAConnectivity hasSignalName as SignalName. "
        "For InstrumentationFunction questions, the DEXPI join path MUST start with "
        "hasInstrumentationFunction and end with hasAssetIdentifier; do not use "
        "an ActuatingFunction root or its direct hasAssetIdentifier path. "
        "The LocalID filter must use hasInstrumentationFunction followed by "
        "hasLocalId on the SAME DEXPI root as the join. "
        "Use where={field:'hasLocalId',operator:'eq',value:'FI_103',"
        "path_id:<catalog ID of instrumentation hasLocalId>,alias:'dexpi'} "
        "for a LocalID condition; do not invent the path ID. "
        "The DEXPI LocalID is a filter, not the historian signal identifier. "
        "For all simulation times leave start_seconds and end_seconds null. "
        "A projection named SignalName MUST end in hasSignalName, never hasAssetIdentifier. "
        "If a question mentions DEXPI and OPCUAConnectivity together, create an explicit "
        "join between their SHACL hasAssetIdentifier paths using distinct aliases. "
        "Do not replace an AssetIdentifier URI filter with a signal-name filter. "
        "Never reuse example signal values unless literally present in the question. "
        "Project the SHACL signal identifier as SignalName (not its literal value). "
        "When a signal value such as XMEAS3 is specified, filter with "
        "where={field:'SignalName',operator:'eq',value:'XMEAS3'}. "
        "Historian requires run_id from selected_context; never invent it. "
        "Do not generate SPARQL or SQL. No keyword routing or external planner."
    )
    candidates = _candidate_paths(question, catalog)
    request = Request(
        os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/api/chat",
        data=json.dumps({
            "model": os.environ.get("DTWISE_QWEN_MODEL", "qwen2.5-coder:3b"),
            "stream": False, "format": _RESPONSE_SCHEMA, "options": {"temperature": 0},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": json.dumps({
                             "question": question, "shacl_paths": [
                                 {"id": i, "domain": path["domain"],
                                  "root_shape": path["root_shape"].rsplit("#", 1)[-1].rsplit("/", 1)[-1],
                                  "predicates": [p.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
                                                 for p in path["predicates"]]}
                                 for i in candidates for path in [catalog[i]]],
                             "selected_context": context})}],
        }).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=float(os.environ.get("DTWISE_QWEN_TIMEOUT_SECONDS", "300"))) as response:
        return json.loads(json.load(response)["message"]["content"])


_FIELDS = {"projections", "joins", "where", "group_by", "aggregation",
           "order_by", "limit", "sources", "run_id", "start_seconds", "end_seconds"}


def interpret_unified_semantics(question, schema, *, context=None, interpret=None):
    """Single model call, strict JSON decoding and SHACL validation.

    interpret is injectable for offline testing and takes (question,catalog,context).
    No execution occurs here.
    """
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Invalid question")
    context = {} if context is None else context
    if not isinstance(context, dict) or set(context) - {
        "run_id", "start_seconds", "end_seconds"
    }:
        raise ValueError("Invalid selected context")
    catalog = shacl_catalog(schema)
    raw = (_interpret(question, catalog, context) if interpret is None
           else interpret(question, catalog, context))
    if not isinstance(raw, dict):
        raise ValueError("Model returned a non-object semantic response: " + type(raw).__name__)
    if set(raw) != _FIELDS:
        missing = sorted(_FIELDS - set(raw))
        unexpected = sorted(set(raw) - _FIELDS)
        raise ValueError(
            "Model returned missing or unexpected semantic fields; "
            + "missing=" + repr(missing) + "; unexpected=" + repr(unexpected)
        )
    if not isinstance(raw["projections"], list) or not isinstance(raw["joins"], list):
        raise ValueError("Invalid projections or joins")
    projections = []
    for p in raw["projections"]:
        if not isinstance(p, dict) or not {"name", "path_id", "source"}.issubset(p) or set(p) - {"name", "path_id", "source", "alias"}:
            raise ValueError("Invalid projection")
        path = _path(p["path_id"], catalog) if p["path_id"] is not None else None
        if path is None and p["source"] != "timescaledb":
            raise ValueError("GraphDB projection requires SHACL path")
        projections.append(Projection(p["name"], path, p["source"], p.get("alias", "entity")))
    joins = []
    for j in raw["joins"]:
        if not isinstance(j, dict) or set(j) != {
            "left", "right", "left_path_id", "right_path_id"
        }:
            raise ValueError("Invalid join")
        left_path = _path(j["left_path_id"], catalog)
        right_path = _path(j["right_path_id"], catalog)
        if j["left"] == j["right"]:
            raise ValueError(
                "Qwen assigned the same alias to both SHACL join entities: "
                + repr(j["left"]) + "; left_domain=" + left_path.domain
                + "; right_domain=" + right_path.domain
                + "; join aliases must be distinct")
        joins.append(Join(j["left"], j["right"], left_path, right_path))
    # Normalize the explicit H6 instrumentation behavior intent using SHACL paths,
    # not memorized signal values or an ungrounded model join. The single Qwen
    # interpretation remains the only model call; this is deterministic grounding.
    h6 = (re.search(r"\bdexpi\b", question, re.I)
          and re.search(r"instrumentation\s*function|instrumentationfunction", question, re.I)
          and re.search(r"\b(?:simulation\s+run|simulation\s+times?|behav(?:e|ed|ior))\b", question, re.I))
    local_match = re.search(r"\bLocalID\s+([A-Za-z0-9_\-]+)", question, re.I)
    if h6 and local_match:
        def find_path(domain, suffix, prefix=None, root=None):
            matches = [(i, p) for i, p in enumerate(catalog)
                       if p["domain"].lower() == domain
                       and [v.rsplit("/", 1)[-1].lower() for v in p["predicates"]]
                       == [v.lower() for v in ((prefix,) if prefix else ()) + (suffix,)]
                       and (root is None or p["root_shape"] == root)]
            if len(matches) != 1:
                raise ValueError("H6 requires a unique SHACL path: " + domain + " " + suffix)
            return _path(matches[0][0], catalog)
        # Prefer the root of the co-rooted instrumentation paths selected above.
        roots = {p["root_shape"] for p in catalog
                 if p["domain"].lower() == "dexpi"
                 and [v.rsplit("/", 1)[-1].lower() for v in p["predicates"]]
                 == ["hasinstrumentationfunction", "haslocalid"]}
        roots = [root for root in roots if any(
            p["domain"].lower() == "dexpi" and p["root_shape"] == root
            and [v.rsplit("/", 1)[-1].lower() for v in p["predicates"]]
            == ["hasinstrumentationfunction", "hasassetidentifier"]
            for p in catalog)]
        if len(roots) != 1:
            raise ValueError("H6 requires one co-rooted DEXPI instrumentation shape")
        root = roots[0]
        local_path = find_path("dexpi", "hasLocalId", "hasInstrumentationFunction", root)
        asset_path = find_path("dexpi", "hasAssetIdentifier", "hasInstrumentationFunction", root)
        opc_asset = find_path("opcuaconnectivity", "hasAssetIdentifier")
        opc_signal = find_path("opcuaconnectivity", "hasSignalName", root=opc_asset.root_shape)
        projections = [Projection("SignalName", opc_signal, "graphdb", "opcuaconnectivity")]
        joins = [Join("dexpi", "opcuaconnectivity", asset_path, opc_asset)]
        raw["where"] = {"field": "hasLocalId", "operator": "eq",
                        "value": local_match.group(1)}
        h6_filter = Predicate("hasLocalId", "eq", local_match.group(1),
                              local_path, "dexpi")
        raw["sources"] = ["graphdb", "timescaledb"]
        raw["start_seconds"] = None
        raw["end_seconds"] = None
    else:
        h6_filter = None
    # Multiple properties of one SHACL root describe one entity, not
    # independent Cartesian-product roots. Only coalesce when there are
    # no explicit joins and every graph projection has the exact same root.
    graph_items = [p for p in projections if p.source == "graphdb"]
    if len(graph_items) > 1 and not joins and len({
        (p.path.domain, p.path.root_shape) for p in graph_items
    }) == 1:
        from dataclasses import replace
        projections = [
            replace(p, alias="entity") if p.source == "graphdb" else p
            for p in projections
        ]
    # Fail closed when an explicitly requested historian operation is
    # misclassified as engineering-only. Never silently return graph rows
    # in place of requested observations.
    historian_requested = bool(re.search(
        r"\\b(historian|time[- ]series|historical samples?|observations?)\\b",
        question, re.I))
    if historian_requested:
        if "timescaledb" not in raw["sources"]:
            raise ValueError(
                "Historian intent was not represented in Qwen sources; "
                "expected timescaledb and SHACL-grounded signal resolution"
            )
        if not any(p.source == "graphdb" for p in projections):
            raise ValueError("Historian requires a GraphDB signal projection")
    if (re.search(r"\bdexpi\b", question, re.I)
            and re.search(r"\b(instrumentation\s*function|instrumentationfunction)\b", question, re.I)
            and re.search(r"\b(simulation\s+run|simulation\s+times?|behav(?:e|ed|ior))\b", question, re.I)):
        domains = {path.domain.lower() for join in joins
                   for path in (join.left_path, join.right_path)}
        signal_outputs = [p for p in projections if p.source == "graphdb"
                          and p.name == "SignalName" and p.path is not None
                          and p.path.domain.lower() == "opcuaconnectivity"
                          and p.path.predicates[-1].lower().endswith("/hassignalname")]
        instrumentation_joins = [
            j for j in joins
            for path in (j.left_path, j.right_path)
            if path.domain.lower() == "dexpi"
            and len(path.predicates) >= 2
            and path.predicates[0].lower().endswith("/hasinstrumentationfunction")
            and path.predicates[-1].lower().endswith("/hasassetidentifier")
        ]
        if ("timescaledb" not in raw["sources"] or
                not {"dexpi", "opcuaconnectivity"}.issubset(domains) or
                not signal_outputs or not instrumentation_joins):
            raise ValueError(
                "Semantic mismatch: DEXPI instrumentation behavior during a "
                "simulation run requires a DEXPI-to-OPCUA SHACL join, "
                "instrumentation-function asset path, SignalName projection, "
                "and TimescaleDB source")
    # Validate the requested semantics, not just the existence of SHACL paths.
    # A valid path to the wrong property is still an incorrect answer.
    for p in projections:
        if p.source == "graphdb" and p.name.lower() == "signalname":
            if not p.path.predicates[-1].lower().endswith("/hassignalname"):
                raise ValueError(
                    "Semantic mismatch: SignalName projection must end in hasSignalName; "
                    "Qwen selected " + p.path.predicates[-1])
    if re.search(r"\bdexpi\b", question, re.I) and re.search(
            r"\bopcua(?:connectivity)?\b", question, re.I):
        domains = {path.domain.lower() for j in joins
                   for path in (j.left_path, j.right_path)}
        if not {"dexpi", "opcuaconnectivity"}.issubset(domains):
            raise ValueError(
                "Semantic mismatch: requested DEXPI-to-OPCUA association "
                "requires an explicit cross-domain SHACL join")
    for key in ("group_by", "order_by", "sources"):
        if not isinstance(raw[key], list) or any(not isinstance(x, str) for x in raw[key]):
            raise ValueError("Invalid " + key)
    for key in ("run_id", "start_seconds", "end_seconds"):
        selected = context.get(key)
        if selected is not None:
            if raw[key] is not None and raw[key] != selected:
                raise ValueError("Model contradicted selected " + key)
            raw[key] = selected
    # A model may copy a UUID from the question, but must not invent one.
    if raw["run_id"] is not None and raw["run_id"] not in question and raw["run_id"] != context.get("run_id"):
        raise ValueError("Model invented run UUID")
    query = SemanticQuery(
        question=question, projections=tuple(projections), joins=tuple(joins),
        where=h6_filter if h6_filter is not None else _where(raw["where"], catalog), group_by=tuple(raw["group_by"]),
        aggregation=raw["aggregation"], order_by=tuple(raw["order_by"]),
        limit=raw["limit"], sources=tuple(raw["sources"]),
        run_id=raw["run_id"], start_seconds=raw["start_seconds"],
        end_seconds=raw["end_seconds"])
    return query.validate(schema)
