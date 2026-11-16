"""Read-only SPARQL compiler for the new unified SHACL semantic IR.

Supported now: graph-only projections, validated graph joins, AND/OR/NOT
filters on projected fields, ordering, and limits. Unsupported semantics fail
closed rather than silently discarding clauses. No old planner is called.
"""
import json
import re

from process_sim.api.unified_semantic_ir import BooleanExpression, Predicate, SemanticQuery

_URI = re.compile(r"^https?://[^\s<>\"{}|^\x60\\]+$")
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _iri(value):
    if not isinstance(value, str) or not _URI.fullmatch(value):
        raise ValueError("SHACL path contains invalid absolute URI")
    return "<" + value + ">"


def _literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        import math
        if not math.isfinite(value):
            raise ValueError("Non-finite filter value")
        return str(value)
    if not isinstance(value, str):
        raise ValueError("Unsupported filter literal")
    return json.dumps(value, ensure_ascii=False)


def _condition(node, fields):
    if isinstance(node, BooleanExpression):
        expressions = [_condition(child, fields) for child in node.children]
        if node.operator == "not":
            return "(!" + expressions[0] + ")"
        return "(" + (" && " if node.operator == "and" else " || ").join(expressions) + ")"
    if not isinstance(node, Predicate) or node.field not in fields:
        raise ValueError("Filter field is not projected")
    var = fields[node.field]
    if node.operator == "exists":
        return "BOUND(" + var + ")"
    val = _literal(node.value)
    if node.operator in ("eq", "ne", "gt", "gte", "lt", "lte"):
        op = {"eq": "=", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[node.operator]
        return "(" + var + " " + op + " " + val + ")"
    if node.operator == "contains":
        return "CONTAINS(STR(" + var + "), " + val + ")"
    if node.operator == "starts_with":
        return "STRSTARTS(STR(" + var + "), " + val + ")"
    if node.operator == "regex":
        return "REGEX(STR(" + var + "), " + val + ")"
    raise ValueError("Unsupported filter operator")


def compile_unified_graph_query(plan: SemanticQuery, *, limit=100):
    """Compile only a validated graph-only query to a bounded SELECT.

    Joins share their explicitly named alias variables. Each join key is a
    separate SHACL path and is equated by a SPARQL FILTER, not guessed.
    """
    if not isinstance(plan, SemanticQuery) or not plan.validated:
        raise ValueError("A validated semantic query is required")
    if plan.sources != ("graphdb",):
        raise ValueError("Cross-source and historian compilation not implemented")
    if plan.aggregation is not None or plan.group_by:
        raise ValueError("Aggregation and grouping not implemented")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("Invalid execution limit")
    if plan.limit is not None:
        limit = min(limit, plan.limit)
    fields = {}
    clauses = []
    alias_shapes = {}
    for projection in plan.projections:
        if projection.source != "graphdb" or projection.path is None:
            raise ValueError("Graph projection requires a SHACL path")
        if not _NAME.fullmatch(projection.name) or projection.name in fields:
            raise ValueError("Projection names must be unique safe identifiers")
        if not _NAME.fullmatch(projection.alias):
            raise ValueError("Invalid entity alias")
        shape = (projection.path.domain, projection.path.root_shape)
        if projection.alias in alias_shapes and alias_shapes[projection.alias] != shape:
            raise ValueError("Entity alias refers to conflicting root shapes")
        alias_shapes[projection.alias] = shape
        current = "?root_" + projection.alias
        for hop, predicate in enumerate(projection.path.predicates):
            next_var = "?v_" + projection.name + "_" + str(hop)
            clauses.append(current + " " + _iri(predicate) + " " + next_var + " .")
            current = next_var
        fields[projection.name] = current
    connected = set()
    for index, join in enumerate(plan.joins):
        if join.left not in alias_shapes or join.right not in alias_shapes:
            raise ValueError("Join references an unbound entity alias")
        for alias, path in ((join.left, join.left_path), (join.right, join.right_path)):
            if alias_shapes[alias] != (path.domain, path.root_shape):
                raise ValueError("Join path does not match entity alias root shape")
        endpoints = []
        for side, alias, path in (("left", join.left, join.left_path),
                                  ("right", join.right, join.right_path)):
            current = "?root_" + alias
            for hop, predicate in enumerate(path.predicates):
                next_var = "?join_" + str(index) + "_" + side + "_" + str(hop)
                clauses.append(current + " " + _iri(predicate) + " " + next_var + " .")
                current = next_var
            endpoints.append(current)
        clauses.append("FILTER(" + endpoints[0] + " = " + endpoints[1] + ")")
        connected.add(frozenset((join.left, join.right)))
    # All projected entity aliases must be connected by explicit joins.
    aliases = set(alias_shapes)
    if len(aliases) > 1:
        reached = {next(iter(aliases))}
        while True:
            expanded = reached | {alias for edge in connected if edge & reached for alias in edge}
            if expanded == reached:
                break
            reached = expanded
        if reached != aliases:
            raise ValueError("Disconnected entity aliases would cause Cartesian product")
    if plan.where is not None:
        clauses.append("FILTER(" + _condition(plan.where, fields) + ")")
    for field in plan.order_by:
        if field not in fields:
            raise ValueError("Ordering field is not projected")
    # SPARQL projection expressions cannot be used with SELECT DISTINCT and
    # arbitrary aliases without GROUP BY in all stores; use a subquery-free
    # BIND form to keep selected aliases visible to ORDER BY and FILTER.
    for name, var in fields.items():
        clauses.append("BIND(" + var + " AS ?" + name + ")")
    query = "SELECT DISTINCT " + " ".join("?" + name for name in fields) + " WHERE {\n"
    query += "\n".join("  " + c for c in clauses) + "\n}"
    if plan.order_by:
        query += "\nORDER BY " + " ".join("?" + name for name in plan.order_by)
    return query + "\nLIMIT " + str(limit)


def execute_unified_graph_query(plan, endpoint, *, executor=None, limit=100):
    """Execute compiler-produced read-only SELECT and return structured rows."""
    from process_sim.dtwise.rdf_executor import execute_select
    sparql = compile_unified_graph_query(plan, limit=limit)
    rows = (executor or execute_select)(endpoint, sparql)
    expected = {p.name for p in plan.projections}
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or set(row) != expected for row in rows
    ):
        raise ValueError("GraphDB returned unexpected columns")
    return {"sparql": sparql, "rows": rows, "count": len(rows),
            "truncated_possible": len(rows) >= min(limit, plan.limit or limit)}
