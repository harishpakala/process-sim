"""Compile schema-verified plans into read-only SPARQL SELECT."""
import re
import json
from process_sim.dtwise.query_planner import validate_hops

LABEL = 'http://www.w3.org/2000/01/rdf-schema#label'


def iri(value):
    if not isinstance(value, str) or not re.fullmatch(r'https?://[^\s<>"{}|\\^`]+', value):
        raise ValueError('Invalid predicate IRI')
    return f'<{value}>'


def _scope_query(query, graph_mode, graph_iri):
    """Scope a complete verified WHERE pattern to one named graph."""
    if graph_mode == "default":
        if graph_iri is not None:
            raise ValueError("graph_iri requires graph_mode=selected")
        return query
    if graph_mode not in ("all_named", "selected"):
        raise ValueError("Unsupported graph mode")
    if graph_mode == "all_named":
        if graph_iri is not None:
            raise ValueError("graph_iri is not allowed for all_named")
        graph = "?graph"
    else:
        graph = iri(graph_iri)
    marker = "WHERE {\n"
    start = query.find(marker)
    if start < 0:
        raise ValueError("Cannot locate query WHERE clause")
    body_start = start + len(marker)
    # Find the matching closing brace, respecting nested UNION/OPTIONAL braces.
    depth = 1
    end = None
    for pos in range(body_start, len(query)):
        if query[pos] == "{":
            depth += 1
        elif query[pos] == "}":
            depth -= 1
            if depth == 0:
                end = pos
                break
    if end is None:
        raise ValueError("Unbalanced WHERE clause")
    body = query[body_start:end].strip("\n")
    wrapped = "  GRAPH " + graph + " {\n" + "\n".join(
        "  " + line for line in body.splitlines()
    ) + "\n  }\n"
    return query[:body_start] + wrapped + query[end:]


def compile_sparql(plan, schema, limit=100, *, graph_mode="default", graph_iri=None, include_graph=False, count_per_graph=False):
    """Compile verified plan; graph_mode: default, all_named, or selected."""
    if plan.get("entity_anchor") == "direct_shacl_target":
        return _compile_direct_shacl_target(plan, schema, limit, graph_mode,
                                            graph_iri, include_graph, count_per_graph)
    if plan.get("join_type") == "identifier_anti_join":
        return _compile_identifier_anti_join(plan, schema, limit, graph_mode,
                                             graph_iri, include_graph, count_per_graph)
    if plan.get("join_type") == "cross_domain_projection":
        from process_sim.dtwise.cross_domain_projection import compile_cross_domain_projection
        return compile_cross_domain_projection(plan, schema, limit, graph_mode, graph_iri,
                                               include_graph, count_per_graph, iri)
    if plan.get("join_type") == "schema_join_graph":
        from process_sim.dtwise.schema_join_graph import compile_schema_join_graph
        return compile_schema_join_graph(plan, schema, limit, graph_mode, graph_iri,
                                         include_graph, count_per_graph, iri)
    if plan.get("join_type") == "schema_bridge_join":
        from process_sim.dtwise.cross_domain_join import compile_schema_bridge_join
        return compile_schema_bridge_join(plan, schema, limit, graph_mode, graph_iri,
                                          include_graph, count_per_graph, iri)
    if plan.get("join_type") is not None:
        if plan['join_type'] == 'multi_key_bridge_join':
            from process_sim.dtwise.cross_domain_join import compile_bridge_join
            return compile_bridge_join(plan, schema, limit, graph_mode, graph_iri,
                                       include_graph, count_per_graph, iri)
        from process_sim.dtwise.cross_domain_join import compile_join
        return compile_join(plan, schema, limit, graph_mode, graph_iri,
                            include_graph, count_per_graph, iri)
    if graph_mode not in ("default", "all_named", "selected"):
        raise ValueError("Unsupported graph mode")
    if graph_mode == "selected":
        iri(graph_iri)
    elif graph_iri is not None:
        raise ValueError("graph_iri requires graph_mode=selected")
    if type(include_graph) is not bool:
        raise ValueError("include_graph must be boolean")
    if include_graph and graph_mode != "all_named":
        raise ValueError("Graph provenance requires graph_mode=all_named")
    if type(count_per_graph) is not bool:
        raise ValueError("count_per_graph must be boolean")
    if count_per_graph:
        if graph_mode != "all_named":
            raise ValueError("Per-graph COUNT requires graph_mode=all_named")
        if plan.get("intent") != "count":
            raise ValueError("Per-graph COUNT requires a count question")
        if include_graph:
            raise ValueError("Use count_per_graph without include_graph for per-graph counts")
    if include_graph and plan.get("ordered_values") is not None:
        raise ValueError("Graph provenance is not supported for ordered distinct values")
    if include_graph and plan.get("intent") == "count":
        raise ValueError("Graph provenance is not supported for aggregate counts")
    query = _scope_query(_compile_unscoped(plan, schema, limit), graph_mode, graph_iri)
    if count_per_graph:
        if plan.get("group_by") is not None:
            raise ValueError("Per-graph grouped counts are not yet supported")
        # Preserve the schema-validated WHERE body, and change only aggregation scope.
        # For terminal-property counts, the existing compiler counts distinct ?value.
        match = re.match(r"SELECT \(COUNT\(DISTINCT (\?entity|\?value)\) AS \?count\)\nWHERE \{", query)
        if not match:
            raise ValueError("Unsupported per-graph COUNT projection")
        variable = match.group(1)
        query = query.replace(f"SELECT (COUNT(DISTINCT {variable}) AS ?count)",
                              f"SELECT ?graph (COUNT(DISTINCT {variable}) AS ?count)", 1)
        query += "\nGROUP BY ?graph\nORDER BY ?graph"
    if include_graph:
        if plan.get("group_by") is not None:
            raise ValueError("Graph provenance is not supported for grouped counts")
        if not query.startswith("SELECT DISTINCT ?entity "):
            raise ValueError("Unsupported provenance projection")
        query = query.replace("SELECT DISTINCT ?entity ", "SELECT DISTINCT ?graph ?entity ", 1)
        if "ORDER BY ?entity " not in query:
            raise ValueError("Unsupported provenance ordering")
        query = query.replace("ORDER BY ?entity ", "ORDER BY ?graph ?entity ", 1)
    return query


def _compile_unscoped(plan, schema, limit=100):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('Result limit must be 1..1000')
    if plan.get('intent') not in ('list','count') or plan.get('query_type') != 'SELECT':
        raise ValueError('Unsupported query operation')
    if plan.get("ordered_values") is not None:
        spec = plan["ordered_values"]
        if (not isinstance(spec, dict) or set(spec) != {"direction", "distinct", "limit"}
                or spec["direction"] not in ("asc", "desc")
                or spec["distinct"] is not True
                or type(spec["limit"]) is not int or not 1 <= spec["limit"] <= 1000):
            raise ValueError("Invalid ordered-value specification")
        if (plan["intent"] != "list" or plan.get("branches") is not None
                or plan.get("group_by") is not None or plan.get("having") is not None
                or plan.get("filters") is not None or plan.get("condition") is not None
                or plan.get("projections") is not None):
            raise ValueError("Ordered values require a single unfiltered property projection")
        domain, root, predicates = plan["domain"], plan["start_shape"], plan["predicates"]
        if not isinstance(predicates, list) or not predicates:
            raise ValueError("Ordered values require an entity traversal")
        valid_path = any(
            hops and hops[-1].get("to_shape") == plan["end_shape"]
            and [h["property"] for h in hops] == predicates
            and [e for h in hops for e in h["evidence_ids"]] == plan["evidence_ids"]
            and validate_hops(hops, schema, root)
            for hops in schema.shacl_paths(root, max_depth=len(predicates), domain=domain))
        if not valid_path:
            raise ValueError("Ordered-value path lacks verified SHACL evidence")
        prop = plan.get("projection")
        if (not isinstance(prop, dict) or prop.get("type") != "terminal_property"
                or prop.get("from_shape") != plan["end_shape"]):
            raise ValueError("Ordered values require a terminal property")
        valid_prop = any(
            len(hops) == 1 and hops[0].get("to_shape") is None
            and hops[0]["property"] == prop.get("predicate")
            and hops[0]["evidence_ids"] == prop.get("evidence_ids")
            and validate_hops(hops, schema, plan["end_shape"])
            for hops in schema.shacl_paths(plan["end_shape"], max_depth=1, domain=domain))
        if not valid_prop:
            raise ValueError("Ordered output property lacks verified SHACL evidence")
        variables = ["?source"] + [f"?node{i}" for i in range(1, len(predicates))] + ["?entity"]
        lines = [f"  {variables[i]} {iri(predicate)} {variables[i+1]} ."
                 for i, predicate in enumerate(predicates)]
        lines.append(f"  ?entity {iri(prop['predicate'])} ?value0 .")
        order = "ASC" if spec["direction"] == "asc" else "DESC"
        return ("SELECT DISTINCT ?value0\nWHERE {\n" + "\n".join(lines)
                + f"\n}}\nORDER BY {order}(?value0)\nLIMIT {spec['limit']}")
    if plan.get("group_by") is not None:
        # Grouped aggregation is deliberately separate from legacy scalar counts.
        if plan.get("intent") != "count" or plan.get("branches") is not None:
            raise ValueError(
                "Grouped aggregation requires a single-path count plan: "
                f"intent={plan.get('intent')!r}, "
                f"branches={plan.get('branches')!r}, "
                f"group_by={plan.get('group_by')!r}"
            )   
        aggregation = plan.get("aggregation")
        if (not isinstance(aggregation, dict)
                or aggregation != {"function": "count", "distinct": True,
                                   "target_variable": "entity"}):
            raise ValueError("Unsupported grouped aggregation")
        keys = plan["group_by"]
        if not isinstance(keys, list) or len(keys) != 1:
            raise ValueError("Exactly one SHACL grouping key is supported")
        if plan.get("projection") is not None or plan.get("projections") is not None:
            raise ValueError("Grouped count cannot mix output projections")
        if plan.get("condition") is not None or plan.get("filters") is not None:
            raise ValueError("Grouped count filters are not yet supported")
        domain, root, predicates = plan["domain"], plan["start_shape"], plan["predicates"]
        if not isinstance(predicates, list) or not predicates:
            raise ValueError("Grouped count requires an entity traversal")
        valid_path = any(
            hops and hops[-1].get("to_shape") == plan["end_shape"]
            and [h["property"] for h in hops] == predicates
            and [e for h in hops for e in h["evidence_ids"]] == plan["evidence_ids"]
            and validate_hops(hops, schema, root)
            for hops in schema.shacl_paths(root, max_depth=len(predicates), domain=domain)
        )
        if not valid_path:
            raise ValueError("Grouped count path lacks verified SHACL evidence")
        key = keys[0]
        if (not isinstance(key, dict) or key.get("type") != "terminal_property"
                or key.get("from_shape") != plan["end_shape"]):
            raise ValueError("Invalid grouping key")
        valid_key = any(
            len(hops) == 1 and hops[0].get("to_shape") is None
            and hops[0]["property"] == key.get("predicate")
            and hops[0]["evidence_ids"] == key.get("evidence_ids")
            and validate_hops(hops, schema, plan["end_shape"])
            for hops in schema.shacl_paths(plan["end_shape"], max_depth=1, domain=domain)
        )
        if not valid_key:
            raise ValueError("Grouping key lacks verified SHACL evidence")
        variables = ["?source"] + [f"?node{i}" for i in range(1, len(predicates))] + ["?entity"]
        lines = [f"  {variables[i]} {iri(predicate)} {variables[i+1]} ."
                 for i, predicate in enumerate(predicates)]
        lines.append(f"  ?entity {iri(key['predicate'])} ?group0 .")
        having = plan.get("having")
        having_clause = ""
        if having is not None:
            if (not isinstance(having, dict) or set(having) != {"function", "operator", "value"}
                    or having["function"] != "count"
                    or having["operator"] not in (">", "<", ">=", "<=", "=")
                    or type(having["value"]) is not int
                    or not 0 <= having["value"] <= 1000000000):
                raise ValueError("Invalid aggregate HAVING condition")
            having_clause = (f"\nHAVING (COUNT(DISTINCT ?entity) "
                             f"{having['operator']} {having['value']})")
        return ("SELECT ?group0 (COUNT(DISTINCT ?entity) AS ?count)\nWHERE {\n"
                + "\n".join(lines) + f"\n}}\nGROUP BY ?group0"
                + having_clause + f"\nORDER BY ?group0\nLIMIT {limit}")
    if "branches" in plan:
        branches = plan["branches"]
        if (not isinstance(branches, list) or not branches
                or (len(branches) < 2 and plan.get("planner") != "shacl_domain_property_union")
                or plan.get("condition") is not None):
            raise ValueError("Invalid multi-path plan")
        domain, root = plan["domain"], plan["start_shape"]
        if plan.get("predicates") or plan.get("evidence_ids") or plan.get("end_shape") is not None:
            raise ValueError("Multi-path plan must not include a competing single path")
        projection = plan.get("projection")
        if projection is not None and (not isinstance(projection, dict)
                or projection.get("type") != "terminal_property"
                or not isinstance(projection.get("predicate"), str)):
            raise ValueError("Invalid multi-path terminal-property projection")
        patterns = []
        for branch in branches:
            if not isinstance(branch, dict):
                raise ValueError("Invalid multi-path branch")
            predicates = branch.get("predicates")
            evidence = branch.get("evidence_ids")
            end_shape = branch.get("end_shape")
            if not isinstance(predicates, list) or not predicates or not isinstance(evidence, list):
                raise ValueError("Invalid multi-path branch structure")
            branch_root = branch.get("start_shape", root)
            if not isinstance(branch_root, str) or not branch_root:
                raise ValueError("UNION branch missing SHACL root")
            valid = any(
                hops and hops[-1].get("to_shape") == end_shape
                and [h["property"] for h in hops] == predicates
                and [e for h in hops for e in h["evidence_ids"]] == evidence
                and validate_hops(hops, schema, branch_root)
                for hops in schema.shacl_paths(branch_root, max_depth=len(predicates), domain=domain)
            )
            if not valid:
                raise ValueError("UNION branch lacks verified SHACL evidence")
            variables = ["?source"] + [f"?branch{len(patterns)}node{i}" for i in range(1, len(predicates))] + ["?entity"]
            triples = [f"    {variables[i]} {iri(p)} {variables[i+1]} ." for i, p in enumerate(predicates)]
            branch_projection = branch.get("projection")
            if projection is not None:
                if (not isinstance(branch_projection, dict)
                        or branch_projection.get("type") != "terminal_property"
                        or branch_projection.get("predicate") != projection["predicate"]
                        or branch_projection.get("from_shape") != end_shape):
                    raise ValueError("UNION branch has incompatible property projection")
                matched = any(
                    len(extension) == 1 and extension[0].get("to_shape") is None
                    and extension[0]["property"] == branch_projection["predicate"]
                    and extension[0]["evidence_ids"] == branch_projection.get("evidence_ids")
                    and validate_hops(extension, schema, end_shape)
                    for extension in schema.shacl_paths(end_shape, max_depth=1, domain=domain)
                )
                if not matched:
                    raise ValueError("UNION property projection lacks verified SHACL evidence")
                triples.append(f"    ?entity {iri(branch_projection['predicate'])} ?value .")
            elif branch_projection is not None:
                raise ValueError("Unexpected UNION branch projection")
            branch_filter = branch.get("filter")
            if branch_filter is not None:
                if projection is not None:
                    raise ValueError("Filtered UNION with projection is not supported")
                if (not isinstance(branch_filter, dict)
                        or branch_filter.get("from_shape") != end_shape):
                    raise ValueError("Invalid UNION filter owner")
                verified = any(
                    len(ext) == 1 and ext[0].get("to_shape") is None
                    and ext[0]["property"] == branch_filter.get("predicate")
                    and ext[0]["evidence_ids"] == branch_filter.get("evidence_ids")
                    and validate_hops(ext, schema, end_shape)
                    for ext in schema.shacl_paths(end_shape, max_depth=1, domain=domain))
                if not verified:
                    raise ValueError("UNION filter lacks terminal SHACL evidence")
                op, value = branch_filter.get("op"), branch_filter.get("value")
                if (op not in ("contains", "contains_ci", "starts_with", "starts_with_ci", "regex", "regex_i")
                        or not isinstance(value, str) or not 1 <= len(value) <= 200
                        or any(ord(ch) < 32 for ch in value)):
                    raise ValueError("Invalid UNION string filter")
                literal = json.dumps(value, ensure_ascii=True)
                variable = "?branchFilter"
                if op == "contains":
                    condition = f"CONTAINS(STR({variable}), {literal})"
                elif op == "contains_ci":
                    condition = f"CONTAINS(LCASE(STR({variable})), LCASE({literal}))"
                elif op == "starts_with":
                    condition = f"STRSTARTS(STR({variable}), {literal})"
                elif op == "starts_with_ci":
                    condition = f"STRSTARTS(LCASE(STR({variable})), LCASE({literal}))"
                else:
                    condition = (f"REGEX(STR({variable}), {literal}, \"i\")"
                                 if op == "regex_i" else f"REGEX(STR({variable}), {literal})")
                triples.append(f"    ?entity {iri(branch_filter['predicate'])} {variable} .")
                triples.append(f"    FILTER(isLiteral({variable}) && {condition})")
            patterns.append("  {\n" + "\n".join(triples) + "\n  }")
        body = "\n  UNION\n".join(patterns)
        if projection is not None:
            if plan["intent"] == "count":
                return "SELECT (COUNT(DISTINCT ?value) AS ?count)\nWHERE {\n" + body + "\n}"
            return ("SELECT DISTINCT ?entity ?value\nWHERE {\n" + body
                    + f"\n}}\nORDER BY ?entity ?value\nLIMIT {limit}")
        if plan["intent"] == "count":
            return "SELECT (COUNT(DISTINCT ?entity) AS ?count)\nWHERE {\n" + body + "\n}"
        return ("SELECT DISTINCT ?entity ?label\nWHERE {\n" + body
                + f"\n  OPTIONAL {{ ?entity <{LABEL}> ?label . }}\n}}\nORDER BY ?entity ?label\nLIMIT {limit}")
    domain, root, predicates = plan['domain'], plan['start_shape'], plan['predicates']
    valid = False
    for hops in schema.shacl_paths(root, max_depth=len(predicates), domain=domain):
        if (hops[-1].get('to_shape') == plan['end_shape'] and
            [h['property'] for h in hops] == predicates and
            [e for h in hops for e in h['evidence_ids']] == plan['evidence_ids'] and
            validate_hops(hops, schema, root)):
            valid = True
            break
    if not valid:
        raise ValueError('Plan does not match verified SHACL structural evidence')
    variables = ['?source'] + [f'?node{i}' for i in range(1,len(predicates))] + ['?entity']
    lines = [f'  {variables[i]} {iri(p)} {variables[i+1]} .' for i,p in enumerate(predicates)]
    if plan.get("projection", {}).get("optional") is True and plan.get("intent") != "list":
        raise ValueError("Optional property projection requires list intent")
    if plan.get("projections") is not None or plan.get("filters") is not None:
        return _compile_structured(plan, schema, limit, lines)
    projection = plan.get('projection')
    if projection is not None:
        if (not isinstance(projection, dict)
                or projection.get('type') != 'terminal_property'
                or projection.get('from_shape') != plan['end_shape']):
            raise ValueError('Invalid terminal-property projection')
        matched = any(
            len(extension) == 1 and extension[0].get('to_shape') is None
            and extension[0]['property'] == projection.get('predicate')
            and extension[0]['evidence_ids'] == projection.get('evidence_ids')
            and validate_hops(extension, schema, plan['end_shape'])
            for extension in schema.shacl_paths(
                plan['end_shape'], max_depth=1, domain=domain)
        )
        if not matched:
            raise ValueError('Property projection lacks verified SHACL evidence')
        if projection.get("optional") not in (None, False, True):
            raise ValueError("Optional projection flag must be boolean")
        triple = f"?entity {iri(projection['predicate'])} ?value ."
        lines.append(f"  OPTIONAL {{ {triple} }}" if projection.get("optional") is True
                     else f"  {triple}")
    condition = plan.get('condition')
    if condition is not None:
        if not isinstance(condition, dict) or condition.get('type') not in ('exists_property', 'lexical_equals') or condition.get('from_shape') != plan['end_shape']:
            raise ValueError('Invalid existence condition')
        matched = any(len(extension) == 1 and extension[0].get('to_shape') is None and
                      extension[0]['property'] == condition.get('predicate') and
                      extension[0]['evidence_ids'] == condition.get('evidence_ids') and
                      validate_hops(extension, schema, plan['end_shape'])
                      for extension in schema.shacl_paths(plan['end_shape'], max_depth=1, domain=domain))
        if not matched:
            raise ValueError('Existence condition lacks verified SHACL evidence')
        lines.append(f"  ?entity {iri(condition['predicate'])} ?conditionValue .")
        if condition['type'] == 'lexical_equals':
            value = condition.get('value')
            if not isinstance(value, str) or not 1 <= len(value) <= 200 or any(ord(c) < 32 for c in value):
                raise ValueError('Invalid comparison literal')
            # STR is lexical matching only, not datatype-aware numeric comparison.
            # isLiteral prevents accidental matching of IRI objects.
            literal = json.dumps(value, ensure_ascii=True)
            lines.append(f'  FILTER(isLiteral(?conditionValue) && STR(?conditionValue) = {literal})')
        elif 'value' in condition:
            raise ValueError('Existence condition cannot carry a comparison value')
    if projection is not None:
        if plan['intent'] == 'count':
            return ('SELECT (COUNT(DISTINCT ?value) AS ?count)\nWHERE {\n'
                    + '\n'.join(lines) + '\n}')
        return ('SELECT DISTINCT ?entity ?value\nWHERE {\n'
                + '\n'.join(lines)
                + f'\n}}\nORDER BY ?entity ?value\nLIMIT {limit}')
    if plan['intent'] == 'count':
        return 'SELECT (COUNT(DISTINCT ?entity) AS ?count)\nWHERE {\n' + '\n'.join(lines) + '\n}'
    return ('SELECT DISTINCT ?entity ?label\nWHERE {\n' + '\n'.join(lines) +
            f'\n  OPTIONAL {{ ?entity <{LABEL}> ?label . }}\n}}\nORDER BY ?entity ?label\nLIMIT {limit}')


def _compile_structured(plan, schema, limit, base_lines):
    """Compile SHACL-verified projection lists and boolean filter trees."""
    domain, end = plan["domain"], plan["end_shape"]
    def check_property(prop):
        if not isinstance(prop, dict) or prop.get("from_shape") != end:
            raise ValueError("Structured property has invalid owning entity")
        if not any(len(h) == 1 and h[0].get("to_shape") is None
                   and h[0]["property"] == prop.get("predicate")
                   and h[0]["evidence_ids"] == prop.get("evidence_ids")
                   and validate_hops(h, schema, end)
                   for h in schema.shacl_paths(end, max_depth=1, domain=domain)):
            raise ValueError("Structured property lacks verified SHACL evidence")
    lines = list(base_lines)
    projections = plan.get("projections")
    if projections is None:
        projections = [plan["projection"]] if plan.get("projection") else []
    if not isinstance(projections, list) or len(projections) > 12:
        raise ValueError("Invalid structured projection list")
    if plan["intent"] == "count" and len(projections) > 1:
        raise ValueError("Multi-property aggregation is not yet supported")
    for i, prop in enumerate(projections):
        check_property(prop)
        if prop.get("optional") not in (None, False, True):
            raise ValueError("Optional projection flag must be boolean")
        triple = f"?entity {iri(prop['predicate'])} ?value{i} ."
        lines.append(f"  OPTIONAL {{ {triple} }}" if prop.get("optional") is True
                     else f"  {triple}")
    counter = [0]
    def compile_filter(node):
        if not isinstance(node, dict):
            raise ValueError("Invalid filter node")
        op = node.get("op")
        if op in ("and", "or"):
            children = node.get("children")
            if not isinstance(children, list) or not 2 <= len(children) <= 8:
                raise ValueError("Invalid filter group")
            fragments = [compile_filter(child) for child in children]
            if op == "and":
                return "\n".join(fragments)
            return "  {\n" + "\n  } UNION {\n".join(fragments) + "\n  }"
        if op not in ("eq", "exists", "not_exists", "contains", "contains_ci", "starts_with", "starts_with_ci", "regex", "regex_i"):
            raise ValueError("Unsupported filter operation")
        check_property(node)
        counter[0] += 1
        variable = f"?filter{counter[0]}"
        triple = f"?entity {iri(node['predicate'])} {variable} ."
        if op == "not_exists":
            return f"  FILTER NOT EXISTS {{ {triple} }}"
        if op == "exists":
            return f"  FILTER EXISTS {{ {triple} }}"
        value = node.get("value")
        if not isinstance(value, str) or not 1 <= len(value) <= 200 or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid filter literal")
        literal = json.dumps(value, ensure_ascii=True)
        if op == "eq":
            predicate = f"STR({variable}) = {literal}"
        elif op == "contains":
            predicate = f"CONTAINS(STR({variable}), {literal})"
        elif op == "contains_ci":
            predicate = f"CONTAINS(LCASE(STR({variable})), LCASE({literal}))"
        elif op == "starts_with":
            predicate = f"STRSTARTS(STR({variable}), {literal})"
        elif op == "starts_with_ci":
            predicate = f"STRSTARTS(LCASE(STR({variable})), LCASE({literal}))"
        elif op in ("regex", "regex_i"):
            predicate = (f"REGEX(STR({variable}), {literal}, \"i\")" if op == "regex_i"
                         else f"REGEX(STR({variable}), {literal})")
        expression = f"isLiteral({variable}) && {predicate}"
        return f"  FILTER EXISTS {{ {triple} FILTER({expression}) }}"
    if plan.get("filters") is not None:
        lines.append(compile_filter(plan["filters"]))
    if plan.get("condition") is not None:
        raise ValueError("Cannot mix structured and legacy filters")
    body = "\n".join(lines)
    if plan["intent"] == "count":
        var = "?value0" if projections else "?entity"
        return f"SELECT (COUNT(DISTINCT {var}) AS ?count)\nWHERE {{\n{body}\n}}"
    if projections:
        values = " ".join(f"?value{i}" for i in range(len(projections)))
        return f"SELECT DISTINCT ?entity {values}\nWHERE {{\n{body}\n}}\nORDER BY ?entity {values}\nLIMIT {limit}"
    return (f"SELECT DISTINCT ?entity ?label\nWHERE {{\n{body}\n"
            f"  OPTIONAL {{ ?entity <{LABEL}> ?label . }}\n}}\nORDER BY ?entity ?label\nLIMIT {limit}")


def _compile_identifier_anti_join(plan, schema, limit, graph_mode, graph_iri,
                                  include_graph, count_per_graph):
    """Compile a two-sided anti-join after revalidating both SHACL join sides.

    Reuse the positive join compiler as the authoritative validator; only
    transform the two validated graph blocks into FILTER NOT EXISTS.
    """
    if (plan.get("query_type") != "SELECT" or plan.get("intent") != "list"
            or plan.get("join_type") != "identifier_anti_join"
            or len(plan.get("sides", [])) != 2):
        raise ValueError("Invalid cross-domain anti-join plan")
    if graph_mode != "all_named" or graph_iri is not None or count_per_graph:
        raise ValueError("Cross-domain anti-join requires all_named graph scope")
    if type(include_graph) is not bool:
        raise ValueError("include_graph must be boolean")
    from process_sim.dtwise.cross_domain_join import compile_join
    validated = dict(plan, join_type="identifier_equality")
    positive = compile_join(validated, schema, limit, graph_mode, graph_iri,
                            False, False, iri)
    where_start = positive.index("WHERE {\n") + len("WHERE {\n")
    body_end = positive.index("\n}\nORDER BY", where_start)
    body = positive[where_start:body_end]
    # Extract the two complete GRAPH clauses, respecting nested UNION blocks.
    blocks = []
    offset = 0
    while offset < len(body):
        while offset < len(body) and body[offset].isspace():
            offset += 1
        if offset == len(body):
            break
        if not body.startswith("GRAPH ?graph", offset):
            raise ValueError("Unexpected validated join graph structure")
        start = offset
        opening = body.index("{", offset)
        depth = 1
        offset = opening + 1
        while offset < len(body) and depth:
            if body[offset] == "{":
                depth += 1
            elif body[offset] == "}":
                depth -= 1
            offset += 1
        if depth:
            raise ValueError("Unbalanced validated join graph structure")
        blocks.append(body[start:offset])
    if len(blocks) != 2 or not blocks[0].startswith("GRAPH ?graph0") or not blocks[1].startswith("GRAPH ?graph1"):
        raise ValueError("Expected exactly two validated join graphs")
    # Target-side entity is existentially scoped; only source entity and key
    # are projected. Include the source graph only when explicitly requested.
    projections = "?entity0 ?assetId" + (" ?graph0" if include_graph else "")
    return (f"SELECT DISTINCT {projections}\nWHERE {{\n  " + blocks[0]
            + "\n  FILTER NOT EXISTS {\n    "
            + blocks[1].replace("\n", "\n    ")
            + "\n  }\n}\nORDER BY ?entity0 ?assetId\n"
            + f"LIMIT {limit}")


def _compile_direct_shacl_target(plan, schema, limit, graph_mode,
                                 graph_iri, include_graph, count_per_graph):
    """Compile indexed subject-level Boolean presence, across graph scopes."""
    if (graph_mode not in ('all_named', 'default', 'selected')
            or (graph_mode == 'selected') != (graph_iri is not None)
            or include_graph or count_per_graph):
        raise ValueError('Unsupported direct SHACL graph options')
    if (type(limit) is not int or not 1 <= limit <= 1000
            or plan.get('query_type') != 'SELECT' or plan.get('intent') != 'list'
            or plan.get('projection') is not None or plan.get('projections') is not None
            or plan.get('condition') is not None or plan.get('branches') is not None
            or plan.get('group_by') is not None):
        raise ValueError('Unsupported direct SHACL target plan')
    filters = plan.get('filters')
    if not isinstance(filters, dict) or filters.get('op') not in ('and', 'or'):
        raise ValueError('Direct target requires explicit Boolean group')
    children = filters.get('children')
    if not isinstance(children, list) or len(children) != 2:
        raise ValueError('Direct target requires two conditions')
    ops = [c.get('op') for c in children if isinstance(c, dict)]
    if len(ops) != 2 or ops[0] != 'exists' or ops[1] not in ('exists', 'not_exists'):
        raise ValueError('Direct target requires positive subject anchor')
    if filters['op'] == 'or' and ops[1] != 'exists':
        raise ValueError('Negated OR requires explicit universe')
    if children[0].get('predicate') == children[1].get('predicate'):
        raise ValueError('Repeated Boolean predicate is not supported')
    for child in children:
        if (set(child) != {'op', 'predicate', 'from_shape', 'evidence_ids'}
                or child['from_shape'] != plan.get('end_shape')):
            raise ValueError('Invalid direct SHACL property owner')
        if not any(len(hops) == 1 and hops[0].get('to_shape') is None
                   and hops[0]['property'] == child['predicate']
                   and hops[0]['evidence_ids'] == child['evidence_ids']
                   and validate_hops(hops, schema, plan['end_shape'])
                   for hops in schema.shacl_paths(plan['end_shape'], max_depth=1,
                                                   domain=plan['domain'])):
            raise ValueError('Direct target property lacks SHACL index evidence')
    def triple(child, variable, graph):
        atom = f'?entity {iri(child["predicate"])} {variable} .'
        if graph_mode == 'all_named':
            return f'GRAPH ?{graph} {{ {atom} }}'
        if graph_mode == 'selected':
            return f'GRAPH {iri(graph_iri)} {{ {atom} }}'
        return atom
    left = triple(children[0], '?positiveValue', 'positiveGraph')
    right = triple(children[1], '?secondValue', 'secondGraph')
    if ops[1] == 'not_exists':
        body = f'  {left}\n  FILTER NOT EXISTS {{ {right} }}'
    elif filters['op'] == 'or':
        body = f'  {{ {left} }}\n  UNION\n  {{ {right} }}'
    else:
        body = f'  {left}\n  {right}'
    return (f'SELECT DISTINCT ?entity\nWHERE {{\n{body}\n}}'
            f'\nORDER BY ?entity\nLIMIT {limit}')
