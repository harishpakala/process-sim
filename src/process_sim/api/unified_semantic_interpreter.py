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


def _where(raw):
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("Invalid Boolean expression; expected object, got " + type(raw).__name__)
    if set(raw) == {"field", "operator", "value"}:
        return Predicate(raw["field"], raw["operator"], raw["value"])
    if set(raw) == {"operator", "children"} and isinstance(raw["children"], list):
        operator, children = raw["operator"], raw["children"]
        valid = (operator == "not" and len(children) == 1) or (
            operator in ("and", "or") and len(children) >= 2)
        if not valid:
            raise ValueError(
                "Qwen produced invalid Boolean arity: operator="
                + repr(operator) + "; child_count=" + str(len(children))
                + "; expected exactly 1 for not or at least 2 for and/or")
        return BooleanExpression(operator, tuple(_where(x) for x in children))
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
        "For historian time-series samples, sources MUST contain both graphdb and timescaledb. "
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
        joins.append(Join(j["left"], j["right"],
                          _path(j["left_path_id"], catalog),
                          _path(j["right_path_id"], catalog)))
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
        where=_where(raw["where"]), group_by=tuple(raw["group_by"]),
        aggregation=raw["aggregation"], order_by=tuple(raw["order_by"]),
        limit=raw["limit"], sources=tuple(raw["sources"]),
        run_id=raw["run_id"], start_seconds=raw["start_seconds"],
        end_seconds=raw["end_seconds"])
    return query.validate(schema)
