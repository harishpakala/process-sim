"""One Qwen interpretation step for engineering, historian and mixed queries.

The model chooses only from SHACL-derived paths. This module does not invoke
an engineering or historian planner, compile SQL/SPARQL, or execute queries.
"""
import json
import os
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
        raise ValueError("Invalid Boolean expression")
    if set(raw) == {"field", "operator", "value"}:
        return Predicate(raw["field"], raw["operator"], raw["value"])
    if set(raw) == {"operator", "children"} and isinstance(raw["children"], list):
        return BooleanExpression(raw["operator"], tuple(_where(x) for x in raw["children"]))
    raise ValueError("Invalid Boolean expression")


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
        "sources: nonempty array containing graphdb and/or timescaledb. "
        "Do not invent paths, IDs, run UUIDs, or simulation times. "
        "Use supplied context for run_id and time boundaries when provided. "
        "Use null for unspecified scalar values, [] for unspecified arrays. "
        "Do not generate SPARQL or SQL. No keyword routing or external planner."
    )
    request = Request(
        os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/api/chat",
        data=json.dumps({
            "model": os.environ.get("DTWISE_QWEN_MODEL", "qwen2.5-coder:3b"),
            "stream": False, "format": "json",
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": json.dumps({
                             "question": question, "shacl_paths": catalog,
                             "selected_context": context})}],
        }).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=90) as response:
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
