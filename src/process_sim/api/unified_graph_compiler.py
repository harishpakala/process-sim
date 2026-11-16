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
    # Qwen sometimes names the projection after the output field while using a
    # domain name for the join alias. Reconcile only when the SHACL root shape
    # uniquely identifies a single join-side alias; never guess between roots.
    join_shapes = {}
    for join in plan.joins:
        for alias, path in ((join.left, join.left_path),
                            (join.right, join.right_path)):
            join_shapes.setdefault((path.domain, path.root_shape), set()).add(alias)
    renames = {}
    for alias, shape in alias_shapes.items():
        matching = join_shapes.get(shape, set())
        if alias not in matching and len(matching) == 1:
            target = next(iter(matching))
            if target in alias_shapes and target != alias:
                raise ValueError("Ambiguous projection and join aliases")
            renames[alias] = target
    if renames:
        for old, new in renames.items():
            old_root, new_root = "?root_" + old, "?root_" + new
            clauses = [clause.replace(old_root + " ", new_root + " ")
                       for clause in clauses]
        alias_shapes = {renames.get(alias, alias): shape
                        for alias, shape in alias_shapes.items()}
    # A joined engineering entity can constrain projected signal rows without
    # itself contributing a SELECT column. Bind its root from the SHACL join path.
    for join in plan.joins:
        for alias, path in ((join.left, join.left_path),
                            (join.right, join.right_path)):
            shape = (path.domain, path.root_shape)
            if alias in alias_shapes and alias_shapes[alias] != shape:
                raise ValueError("Join alias conflicts with projected root shape: " + alias)
            alias_shapes.setdefault(alias, shape)
    connected = set()
    # Reuse variables for common SHACL path prefixes on the same entity.
    # Otherwise LocalID could match a different function under the same root.
    path_prefixes = {}
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
                key = (alias, tuple(path.predicates[:hop + 1]))
                next_var = path_prefixes.setdefault(
                    key, "?join_" + str(index) + "_" + side + "_" + str(hop))
                triple = current + " " + _iri(predicate) + " " + next_var + " ."
                if triple not in clauses:
                    clauses.append(triple)
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
        # Materialize explicit SHACL filter paths from their already-bound entity root.
        # The filter is not projected and must never create an independent root.
        def bind_filter_paths(node):
            if isinstance(node, BooleanExpression):
                for child in node.children:
                    bind_filter_paths(child)
            elif node.path is not None:
                shape = (node.path.domain, node.path.root_shape)
                if alias_shapes.get(node.alias) != shape:
                    raise ValueError("Filter path does not share a bound entity root")
                key = (node.alias, shape, node.path.predicates)
                if key not in path_filters:
                    current = "?root_" + node.alias
                    idx = len(path_filters)
                    for hop, predicate in enumerate(node.path.predicates):
                        prefix = (node.alias, tuple(node.path.predicates[:hop + 1]))
                        next_var = path_prefixes.setdefault(
                            prefix, "?filter_" + str(idx) + "_" + str(hop))
                        triple = current + " " + _iri(predicate) + " " + next_var + " ."
                        if triple not in clauses:
                            clauses.append(triple)
                        current = next_var
                    path_filters[key] = current
                filter_vars[id(node)] = path_filters[key]
        path_filters = {}
        filter_vars = {}
        bind_filter_paths(plan.where)
        # A join key can be filtered without appearing in SELECT. Only expose
        # a name when it resolves to one unique SHACL join property.
        filter_fields = dict(fields)
        for index, join in enumerate(plan.joins):
            for side, path in (("left", join.left_path),
                               ("right", join.right_path)):
                terminal = path.predicates[-1].rsplit("#", 1)[-1].rsplit("/", 1)[-1]
                variable = "?join_" + str(index) + "_" + side + "_" + str(len(path.predicates) - 1)
                if terminal not in filter_fields:
                    filter_fields[terminal] = variable
                elif filter_fields[terminal] != variable and terminal not in fields:
                    # Multiple join keys with this name must be equivalent;
                    # a two-sided equality join is already enforced above.
                    if not (side == "right" and
                            join.left_path.predicates[-1].rsplit("/", 1)[-1]
                            == terminal and
                            filter_fields[terminal] ==
                            "?join_" + str(index) + "_left_" + str(len(join.left_path.predicates) - 1)):
                        raise ValueError("Ambiguous non-projected filter field: " + terminal)
        def condition_with_paths(node):
            if isinstance(node, BooleanExpression):
                children = [condition_with_paths(c) for c in node.children]
                if node.operator == "not":
                    return "(!" + children[0] + ")"
                return "(" + (" && " if node.operator == "and" else " || ").join(children) + ")"
            if node.path is not None:
                return _condition(Predicate(node.field, node.operator, node.value),
                                  {node.field: filter_vars[id(node)]})
            return _condition(node, filter_fields)
        clauses.append("FILTER(" + condition_with_paths(plan.where) + ")")
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
