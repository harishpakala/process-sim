"""Execute only compiler-produced read-only SPARQL against GraphDB."""
from urllib.parse import urlparse
import requests


def execute_select(endpoint, sparql, timeout=30):
    parsed = urlparse(endpoint)
    if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError('Endpoint must be a valid HTTP(S) URL without embedded credentials')
    if not isinstance(timeout, (int,float)) or timeout <= 0:
        raise ValueError('Timeout must be positive')
    if not sparql.lstrip().upper().startswith('SELECT '):
        raise ValueError('Only generated SELECT queries are supported')
    response = requests.post(endpoint, data={'query':sparql},
                             headers={'Accept':'application/sparql-results+json'}, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data.get('results',{}).get('bindings'),list):
        raise ValueError('Endpoint did not return SPARQL SELECT bindings')
    return [{key:value.get('value') for key,value in row.items()} for row in data['results']['bindings']]


def build_answer(bindings, plan, limit=100, *, include_graph=False, count_per_graph=False):
    """Format entity results or SHACL-grounded terminal-property projections."""

    if plan.get("join_type") == "identifier_anti_join":
        if plan.get("intent") != "list" or count_per_graph:
            raise ValueError("Invalid cross-domain anti-join result mode")
        expected = {"entity0", "assetId"} | ({"graph0"} if include_graph else set())
        unique = set()
        for binding in bindings:
            if set(binding) != expected or any(binding[key] is None for key in expected):
                raise ValueError("Unexpected or unbound cross-domain anti-join result")
            unique.add(tuple(binding[key] for key in
                             (["graph0"] if include_graph else []) + ["entity0", "assetId"]))
        records = []
        for record in sorted(unique):
            if include_graph:
                graph, entity, key = record
                records.append({"source_graph": graph, "entity": entity,
                                "asset_identifier": key})
            else:
                entity, key = record
                records.append({"entity": entity, "asset_identifier": key})
        return {"count": len(records), "entities": records,
                "join_type": "identifier_anti_join", "join_key": plan["key_label"],
                "source_domain": plan["sides"][0]["domain"],
                "target_domain": plan["sides"][1]["domain"],
                "truncated_possible": len(bindings) >= limit}

    # Cross-domain terminal-property results have source/target branches, not
    # a single end_shape.  The compiler projects ?value and optionally graphs.
    if plan.get("join_type") == "cross_domain_projection":
        if plan.get("intent") != "list" or count_per_graph:
            raise ValueError("Unsupported cross-domain projection result mode")
        if include_graph and not all("graph0" in row and "graph1" in row for row in bindings):
            raise ValueError("Cross-domain provenance requires both graph bindings")
        expected = {"value", "graph0", "graph1"} if include_graph else {"value"}
        values = set()
        for row in bindings:
            if set(row) != expected or any(row[key] is None for key in expected):
                raise ValueError("Unexpected cross-domain projection bindings: " + repr(sorted(row)))
            if include_graph:
                values.add((row["value"], row["graph0"], row["graph1"]))
            else:
                values.add(row["value"])
        records = ([{"value": v, "source_graph": g0, "target_graph": g1}
                    for v, g0, g1 in sorted(values)] if include_graph
                   else sorted(values))
        return {
            "count": len(records), "values": records,
            "intent": "list", "join_type": "cross_domain_projection",
            "join_key": plan.get("join_key_label"),
            "source_domain": plan["source"]["domain"],
            "target_domain": plan["target"]["domain"],
            "property": plan["projection"]["predicate"],
            "entity_type": plan["target"]["end_shape"],
            "truncated_possible": len(bindings) >= limit,
        }

    # Multi-hop joins project product attributes from a different domain than
    # the source entity. Their result columns intentionally omit ?entity.
    if plan.get("join_type") == "shacl_multihop_identifier_join":
        if plan.get("intent") != "list" or count_per_graph:
            raise ValueError("Unsupported multihop result mode")
        projections = plan.get("projections")
        sides = plan.get("sides")
        if (not isinstance(projections, list) or not 1 <= len(projections) <= 12
                or not isinstance(sides, list) or len(sides) != 3
                or not all(isinstance(p, dict) and isinstance(p.get("predicate"), str)
                           and p.get("predicate") for p in projections)):
            raise ValueError("Invalid multihop projection plan")
        predicates = [p["predicate"] for p in projections]
        if len(set(predicates)) != len(predicates):
            raise ValueError("Duplicate multihop projection predicates")
        columns = [f"value{i}" for i in range(len(projections))]
        graphs = [f"graph{i}" for i in range(3)] if include_graph else []
        expected = set(columns + graphs)
        records = set()
        required = {f"value{i}" for i, p in enumerate(projections)
                    if p.get("label") in plan.get("join_keys", [])} | set(graphs)
        for row in bindings:
            if (not set(row).issubset(expected) or not required.issubset(row)
                    or any(row[key] is None for key in required)
                    or any(value is None for value in row.values())):
                raise ValueError("Unexpected or unbound multihop projection columns")
            records.add(tuple(row.get(key) for key in graphs + columns))
        rows = []
        for record in sorted(records, key=lambda values: tuple(
                (v is None, "" if v is None else str(v)) for v in values)):
            item = {"properties": dict(zip(predicates, record[len(graphs):]))}
            if include_graph:
                item["source_graph"], item["bridge_graph"], item["target_graph"] = record[:3]
            rows.append(item)
        return {"count": len(rows), "values": rows, "intent": "list",
                "join_type": "shacl_multihop_identifier_join",
                "source_domain": sides[0]["domain"],
                "bridge_domain": sides[1]["domain"],
                "target_domain": sides[2]["domain"],
                "properties": predicates,
                "truncated_possible": len(bindings) >= limit}

    # Handle cross-domain JOINs before single-domain logic.
    if plan.get("join_type") in ("identifier_equality", "multi_key_bridge_join", "schema_bridge_join", "schema_join_graph"):
        return build_join_answer(bindings, plan)

    projection = plan.get('projection')
    projections = plan.get('projections')
    is_property = isinstance(projection, dict) and projection.get('type') == 'terminal_property'
    # The compiler names the first structured projection ?value0.  Validate
    # the returned columns rather than comparing plan metadata dictionaries:
    # those dictionaries can differ even for the same terminal predicate.

    if count_per_graph:
        if plan.get('intent') != 'count':
            raise ValueError('Per-graph formatting requires count intent')
        rows = []
        seen = set()
        for binding in bindings:
            graph = binding.get('graph')
            value = binding.get('count')
            if not graph or value is None:
                raise ValueError('Per-graph COUNT must return ?graph and ?count')
            if graph in seen:
                raise ValueError('Per-graph COUNT returned duplicate graph groups')
            seen.add(graph)
            rows.append({'graph': graph, 'count': int(value)})
        rows.sort(key=lambda row: row['graph'])
        result = {'intent': 'count_per_graph', 'counts': rows,
                  'graph_count': len(rows), 'entity_type': plan.get('end_shape')}
        if is_property:
            result.update({'projection': 'terminal_property',
                           'property': projection['predicate'], 'counted': 'distinct_values'})
        return result

    # Grouped aggregates may return no rows when HAVING eliminates every group.
    # They are not scalar COUNT results and must retain their group keys.
    if plan.get('intent') == 'count' and plan.get('group_by'):
        groups = plan['group_by']
        if not isinstance(groups, list) or not groups:
            raise ValueError('Invalid grouped COUNT plan')
        keys = [f'group{i}' for i in range(len(groups))]
        expected = set(keys + ['count']) | ({'graph'} if include_graph else set())
        rows = []
        seen = set()
        for binding in bindings:
            if set(binding) != expected or any(binding[k] is None for k in expected):
                raise ValueError('Grouped COUNT returned unexpected or unbound columns')
            group_values = tuple(binding[k] for k in keys)
            identity = ((binding['graph'],) if include_graph else ()) + group_values
            if identity in seen:
                raise ValueError('Grouped COUNT returned duplicate groups')
            seen.add(identity)
            row = {'groups': dict(zip((g['predicate'] for g in groups), group_values)),
                   'count': int(binding['count'])}
            if include_graph:
                row['graph'] = binding['graph']
            rows.append(row)
        rows.sort(key=lambda row: (row.get('graph', ''), tuple(row['groups'].values())))
        return {'count': len(rows), 'values': rows, 'intent': 'grouped_count',
                'entity_type': plan['end_shape'],
                'truncated_possible': len(bindings) >= limit}

    # Ordered/distinct property queries intentionally project only ?value0.
    if is_property and plan.get('ordered_values'):
        if plan.get('intent') != 'list':
            raise ValueError('Ordered property projection requires list intent')
        expected = {'value0'} | ({'graph'} if include_graph else set())
        values = set()
        for binding in bindings:
            if set(binding) != expected or any(binding[k] is None for k in expected):
                raise ValueError('Ordered property query returned unexpected columns')
            values.add((binding['graph'], binding['value0']) if include_graph else binding['value0'])
        ordered = plan['ordered_values']
        if ordered.get('direction') not in ('asc', 'desc'):
            raise ValueError('Unsupported ordering direction')
        rows = sorted(values, reverse=ordered['direction'] == 'desc')
        records = ([{'graph': g, 'value': v} for g, v in rows]
                   if include_graph else rows)
        return {'count': len(records), 'values': records, 'intent': 'list',
                'projection': 'terminal_property', 'property': projection['predicate'],
                'entity_type': plan['end_shape'],
                'truncated_possible': len(bindings) >= ordered.get('limit', limit)}

    if plan['intent'] == 'count':
        if not bindings or 'count' not in bindings[0]:
            raise ValueError('COUNT query did not return ?count')
        result = {'count': int(bindings[0]['count']),
                  'entity_type': plan['end_shape'], 'intent': 'count'}
        if is_property:
            result['projection'] = 'terminal_property'
            result['property'] = projection['predicate']
            result['counted'] = 'distinct_values'
        return result

    # Structured multi-property SELECT: compiler emits ?value0, ?value1, ...
    # in the same order as plan["projections"]. Preserve the complete
    # predicate URI as the output key to avoid label/local-name collisions.
    if isinstance(projections, list) and len(projections) > 1:
        if not all(isinstance(p, dict) and p.get('type') == 'terminal_property'
                   and isinstance(p.get('predicate'), str) and p['predicate']
                   for p in projections):
            raise ValueError('Invalid structured terminal-property projections')
        predicates = [p['predicate'] for p in projections]
        if len(set(predicates)) != len(predicates):
            raise ValueError('Duplicate structured projection predicates')
        columns = [f'value{i}' for i in range(len(projections))]
        expected = set(columns) | {'entity'} | ({'graph'} if include_graph else set())
        records = set()
        for row in bindings:
            if set(row) != expected:
                raise ValueError(
                    'Multi-property query returned unexpected binding variables; '
                    f'expected: {sorted(expected)}; actual: {sorted(row)}'
                )
            if any(row[key] is None for key in expected):
                raise ValueError('Multi-property query returned an unbound variable')
            records.add(tuple(row[key] for key in
                              (['graph'] if include_graph else []) + ['entity'] + columns))
        rows = []
        for record in sorted(records):
            offset = 1 if include_graph else 0
            item = {'entity': record[offset],
                    'properties': dict(zip(predicates, record[offset + 1:]))}
            if include_graph:
                item = {'graph': record[0], **item}
            rows.append(item)
        return {
            'count': len(rows), 'values': rows,
            'entity_type': plan['end_shape'],
            'properties': predicates, 'projection': 'multiple_properties',
            'truncated_possible': len(bindings) >= limit,
            'note': 'Listing count is limited by LIMIT; use a count question for total distinct values.'
        }

    if is_property:
        values = set()
        for row in bindings:
            # A terminal-property SELECT must return both ?entity and ?value.
            # Do not silently convert a malformed response to an entity listing.
            if 'entity' not in row:
                raise ValueError('Terminal-property query must return ?entity')
            # Only one projected value column is supported by this formatter.
            # Never silently discard extra structured projection columns.
            value_columns = [key for key in row if key == 'value' or
                             (key.startswith('value') and key[5:].isdigit())]
            optional = projection.get('optional') is True
            if optional and not value_columns:
                entity = row['entity']
                if entity is None:
                    raise ValueError('Optional-property query returned an unbound entity')
                if include_graph:
                    graph = row.get('graph')
                    if not graph:
                        raise ValueError('Provenance query must return ?graph')
                    values.add((graph, entity, None))
                else:
                    values.add((entity, None))
                continue
            if len(value_columns) != 1 or value_columns[0] not in ('value', 'value0'):
                raise ValueError(
                    'Terminal-property query must return ?entity and exactly one '
                    '?value or ?value0 column; '
                    f'actual binding variables: {sorted(row)}'
                )
            value = row[value_columns[0]]
            entity = row['entity']
            if entity is None or (value is None and not optional):
                raise ValueError('Terminal-property query returned an unbound entity or value')
            if include_graph:
                graph = row.get('graph')
                if not graph:
                    raise ValueError('Provenance query must return ?graph')
                values.add((graph, entity, value))
            else:
                values.add((entity, value))
        if include_graph:
            rows = [{'graph': graph, 'entity': entity, 'value': value}
                    for graph, entity, value in sorted(values, key=lambda r: tuple("" if x is None else x for x in r))]
        else:
            rows = [{'entity': entity, 'value': value}
                    for entity, value in sorted(values, key=lambda r: tuple("" if x is None else x for x in r))]
        return {
            'count': len(rows),
            'values': rows,
            'entity_type': plan['end_shape'],
            'property': projection['predicate'],
            'projection': 'terminal_property',
            'truncated_possible': len(bindings) >= limit,
            'note': 'Listing count is limited by LIMIT; use a count question for total distinct values.'
        }

    entities = {}
    for row in bindings:
        uri = row.get('entity')
        if uri:
            graph = row.get('graph') if include_graph else None
            if include_graph and not graph:
                raise ValueError('Provenance query must return ?graph')
            key = (graph, uri) if include_graph else uri
            item = entities.setdefault(key, {'uri': uri, 'label': None, **({'graph': graph} if include_graph else {})})
            if item['label'] is None and row.get('label'):
                item['label'] = row['label']
    rows = sorted(entities.values(), key=lambda item: (item.get('graph', ''), item['label'] or '', item['uri']))
        # Cross-domain JOIN results have two endpoints, not one end_shape.
    if plan.get("join_type") == "identifier_equality":
        return {
            "count": len(rows),
            "entities": rows,
            "entity_type": [
                side.get("target_label", "multiple")
                for side in plan["sides"]
            ],
            "join_type": plan["join_type"],
            "join_key": plan.get("key_label"),
        }
    return {'count': len(rows), 'entities': rows, 'entity_type': plan['end_shape'],
            'truncated_possible': len(bindings) >= limit,
            'note': 'Listing count is limited by LIMIT; use a count question for total instances.'}



def build_join_answer(bindings, plan):
    """Format N-domain identifier-equality JOIN results."""

    sides = plan["sides"]

    if len(sides) < 2:
        raise ValueError("Identifier-equality JOIN requires at least two domains")

    domains = [side["domain"] for side in sides]

    if len(set(domains)) != len(domains):
        raise ValueError("JOIN plan contains duplicate domains")

    def value(binding, variable):
        item = binding.get(variable)

        if isinstance(item, dict):
            return item.get("value")

        if item is None:
            return None

        if isinstance(item, str):
            return item

        return str(item)

    matches = []

    for binding in bindings:
        if plan['join_type'] in ('schema_bridge_join', 'schema_join_graph'):
            keys = plan['join_keys']
            key_values = [value(binding, f'joinKey{i}') for i in range(len(keys))]
            if not all(key_values):
                raise ValueError('Generic bridge JOIN is missing a join key')
            record = {'join_identifiers': dict(zip(keys, key_values))}
        else:
            record = None
        asset_id = value(binding, "assetId") if record is None else None

        if record is None:
            if not asset_id:
                raise ValueError("JOIN result is missing ?assetId")
            record = {"asset_identifier": asset_id}
        if plan["join_type"] == "multi_key_bridge_join":
            product_id = value(binding, "productId")
            if not product_id:
                raise ValueError("Bridge JOIN result is missing ?productId")
            record["product_identifier"] = product_id

        for index, domain in enumerate(domains):
            entity_var = f"entity{index}"
            graph_var = f"graph{index}"

            entity = value(binding, entity_var)

            if not entity:
                raise ValueError(
                    f"JOIN result is missing ?{entity_var} "
                    f"for domain {domain}"
                )

            record[f"{domain}_entity"] = entity

            if graph_var in binding:
                graph = value(binding, graph_var)

                if not graph:
                    raise ValueError(
                        f"JOIN result has an unbound ?{graph_var}"
                    )

                record[f"{domain}_graph"] = graph

        matches.append(record)

    return {
        "count": len(matches),
        "join_type": plan["join_type"],
        "join_key": plan.get("key_label", plan.get("join_keys", [None])[0]),
        **({"join_keys": plan['join_keys'], "bridge_domain": plan['bridge_domain']}
           if plan["join_type"] == "schema_bridge_join" else {}),
        **({"join_keys": plan["join_keys"], "bridge_domains": plan["bridge_domains"]}
           if plan["join_type"] == "schema_join_graph" else {}),
        **({"join_keys": [plan["key_label"], plan["product_key_label"]],
           "bridge_domain": plan["bridge_domain"]}
          if plan["join_type"] == "multi_key_bridge_join" else {}),
        "domains": domains,
        "matches": matches,
    }
