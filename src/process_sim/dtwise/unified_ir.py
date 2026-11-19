"""Unified, evidence-checked query IR compiler for multi-domain and N-hop RDF queries.

This module is deliberately independent of Ollama: a semantic model emits the IR,
then this module validates every edge/property against the schema and compiles SPARQL.
No implicit cross-domain equality is inferred from matching property names.
"""
import json
import re

_IRI = re.compile(r'https?://[^\s<>"{}|\\^`]+\Z')
_ALIAS = re.compile(r'[A-Za-z][A-Za-z0-9_]{0,39}\Z')


def _iri(s):
    if not isinstance(s, str) or not _IRI.fullmatch(s):
        raise ValueError('Invalid IRI: %r' % (s,))
    return '<' + s + '>'


def _alias(s):
    if not isinstance(s, str) or not _ALIAS.fullmatch(s):
        raise ValueError('Invalid alias: %r' % (s,))
    return s


def _literal(s):
    if not isinstance(s, str) or len(s) > 1000 or any(ord(c) < 32 for c in s):
        raise ValueError('Invalid string literal')
    return json.dumps(s, ensure_ascii=True)


def _schema_dict(schema):
    if isinstance(schema, dict):
        return schema
    if isinstance(schema, str):
        with open(schema, encoding='utf-8') as f:
            return json.load(f)
    raise TypeError('Pass the JSON schema index dictionary or its filename')


def _check_shape_property(index, domain, shape, predicate):
    matches = [x for x in index['shape_paths'] if x['domain'] == domain
               and x['node_shape'] == shape and x['path'] == predicate
               and x.get('evidence')]
    if len(matches) != 1:
        candidates = sorted({x['node_shape'] for x in index['shape_paths']
                             if x['domain'] == domain and x['path'] == predicate
                             and x.get('evidence')})
        raise ValueError('Property lacks unique SHACL evidence: %s %s; '
                         'requested source shape=%s; matching source shapes=%s' %
                         (domain, predicate, shape, json.dumps(candidates)))
    return matches[0]['evidence']


def validate_ir(ir, schema, *, mappings=None):
    """Return a validated copy; mappings is an independently verified join registry.

    Mapping registry records: {id, left_domain, right_domain, left_property,
    right_property, evidence_ids:[...], verified:true}. The registry is external
    because the supplied schema index has no verified cross-domain mappings.
    """
    idx = _schema_dict(schema)
    if not isinstance(ir, dict) or ir.get('ir_version') != '1.0':
        raise ValueError('Expected unified IR version 1.0')
    domain_both = ir.get('domain_both_properties')
    if domain_both is not None:
        if not isinstance(domain_both, dict) or set(domain_both) != {
                'domain', 'properties', 'paths'}:
            raise ValueError('Invalid domain both-properties query')
        domain = domain_both['domain']
        names = domain_both['properties']
        groups = domain_both['paths']
        if (not isinstance(domain, str) or not domain
                or not isinstance(names, list) or len(names) != 2
                or not all(isinstance(n, str) and n for n in names)
                or names[0].casefold() == names[1].casefold()
                or not isinstance(groups, list) or len(groups) != 2):
            raise ValueError('Invalid domain both-properties fields')
        for name, paths in zip(names, groups):
            if not isinstance(paths, list) or not paths or len(paths) > 256:
                raise ValueError('Invalid domain both-properties paths')
            eligible = sorted({
                (x['node_shape'], x['path'])
                for x in idx['shape_paths']
                if x['domain'] == domain and x.get('evidence')
                and x['path'].rsplit('/', 1)[-1].rsplit('#', 1)[-1].casefold()
                in {name.casefold(), ('has' + name).casefold()}
            })
            if (not all(isinstance(p, list) and len(p) == 2
                        and all(isinstance(v, str) for v in p) for p in paths)
                    or sorted(tuple(p) for p in paths) != eligible):
                raise ValueError('Both-properties paths must equal evidenced owners')
        if (ir.get('entities') != [] or ir.get('edges') != []
                or ir.get('projections') != [] or ir.get('filters') is not None
                or ir.get('operation', {}).get('type') != 'select'
                or ir.get('return_entities') is not True
                or ir.get('order_by') or ir.get('result_limit') is not None
                or ir.get('domain_regex') is not None):
            raise ValueError('Unsupported domain both-properties modifiers')
        return ir
    domain_regex = ir.get('domain_regex')
    if domain_regex is not None:
        if not isinstance(domain_regex, dict) or set(domain_regex) != {
                'domain', 'property', 'pattern', 'paths'}:
            raise ValueError('Invalid domain regex query')
        domain, prop, pattern = (domain_regex[k] for k in
                                 ('domain', 'property', 'pattern'))
        if not all(isinstance(x, str) and x for x in (domain, prop, pattern)):
            raise ValueError('Invalid domain regex fields')
        if len(pattern) > 256 or any(ord(c) < 32 for c in pattern):
            raise ValueError('Invalid regex pattern')
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError('Invalid regex pattern') from exc
        paths = domain_regex['paths']
        if not isinstance(paths, list) or not paths or len(paths) > 256:
            raise ValueError('Invalid domain regex shape paths')
        eligible = sorted({
            (x['node_shape'], x['path'])
            for x in idx['shape_paths']
            if x['domain'] == domain and x.get('evidence')
            and (x['path'].rsplit('/', 1)[-1].rsplit('#', 1)[-1]
                 .removeprefix('has').casefold() == prop.casefold()
                 or x['path'].rsplit('/', 1)[-1].rsplit('#', 1)[-1]
                 .casefold() == prop.casefold())
        })
        if sorted(tuple(x) for x in paths if isinstance(x, list) and len(x) == 2) != eligible or len(paths) != len(eligible):
            raise ValueError('Domain regex paths must equal all evidenced shape owners')
        if (ir.get('edges') or ir.get('projections') or ir.get('filters') is not None
                or ir.get('operation', {'type': 'select'}).get('type') != 'select'
                or ir.get('return_entities') is not True
                or ir.get('order_by') or ir.get('result_limit') is not None):
            raise ValueError('Unsupported domain regex query modifiers')
        return ir
    entities = ir.get('entities')
    if not isinstance(entities, list) or not 1 <= len(entities) <= 24:
        raise ValueError('entities must contain 1..24 nodes')
    nodes = {}
    for n in entities:
        a = _alias(n['alias'])
        if a in nodes:
            raise ValueError('Duplicate entity alias')
        if not isinstance(n.get('domain'), str) or not isinstance(n.get('shape'), str):
            raise ValueError('Entity must specify domain and shape')
        if not any(x['domain'] == n['domain'] and x['node_shape'] == n['shape']
                   for x in idx['shape_paths']):
            raise ValueError('Entity shape not present in indexed SHACL: ' + a)
        nodes[a] = n
    def prop(ref):
        if not isinstance(ref, dict):
            raise ValueError('Property reference must be an object')
        n = nodes.get(ref.get('entity'))
        if not n:
            raise ValueError('Unknown entity in property reference')
        return _check_shape_property(idx, n['domain'], n['shape'], ref.get('predicate'))
    edges = ir.get('edges', [])
    if not isinstance(edges, list) or len(edges) > 64:
        raise ValueError('Invalid edge list')
    registry = {m['id']: m for m in (mappings or [])}
    graph = {a: set() for a in nodes}
    for e in edges:
        left, right = e.get('from'), e.get('to')
        if left not in nodes or right not in nodes or left == right:
            raise ValueError('Edge has invalid endpoints')
        graph[left].add(right); graph[right].add(left)
        kind = e.get('kind')
        if kind == 'shacl':
            if nodes[left]['domain'] != nodes[right]['domain']:
                raise ValueError('Cross-domain SHACL edge forbidden without mapping evidence')
            prop({'entity': left, 'predicate': e.get('predicate')})
            # The target must be explicitly linked by a SHACL sh:node constraint.
            # A bare terminal property cannot authorize an entity-to-entity hop.
            p = e['predicate']
            relation = [x for x in idx['relationships'] if x['domain'] == nodes[left]['domain']
                        and x['predicate'] == 'http://www.w3.org/ns/shacl#node'
                        and x['object'] == nodes[right]['shape']]
            matching_property_shapes = {x['property_shape'] for x in idx['shape_paths']
                                        if x['node_shape'] == nodes[left]['shape'] and x['path'] == p}
            if not any(x['subject'] in matching_property_shapes for x in relation):
                raise ValueError('SHACL hop has no verified sh:node target')
        elif kind == 'mapping':
            m = registry.get(e.get('mapping_id'))
            if not m or m.get('verified') is not True or not m.get('evidence_ids'):
                raise ValueError('Unverified cross-domain mapping')
            if (m.get('left_domain') != nodes[left]['domain'] or
                    m.get('right_domain') != nodes[right]['domain'] or
                    m.get('left_property') != e.get('left_predicate') or
                    m.get('right_property') != e.get('right_predicate')):
                raise ValueError('Mapping evidence does not match edge')
            prop({'entity': left, 'predicate': e['left_predicate']})
            prop({'entity': right, 'predicate': e['right_predicate']})
        else:
            raise ValueError('Unsupported edge kind')
    seen = {next(iter(nodes))}; pending = list(seen)
    while pending:
        for neighbor in graph[pending.pop()]:
            if neighbor not in seen:
                seen.add(neighbor); pending.append(neighbor)
    if seen != set(nodes):
        raise ValueError('Disconnected query graph: no Cartesian products allowed')
    anti = ir.get('anti_join')
    if anti is not None:
        if (not isinstance(anti, dict) or set(anti) != {'from', 'to'}
                or len(nodes) != 2 or len(edges) != 1
                or edges[0].get('kind') != 'mapping'
                or anti['from'] != edges[0]['from']
                or anti['to'] != edges[0]['to']):
            raise ValueError('Anti-join requires one verified directed mapping edge')
        if ir.get('filters') is not None or ir.get('projections'):
            raise ValueError('Anti-join does not support filters or projections')
        if ir.get('operation', {'type': 'select'}).get('type') != 'select':
            raise ValueError('Anti-join requires SELECT')
        if ir.get('return_entities') is not True:
            raise ValueError('Anti-join requires return_entities=true')
        if ir.get('order_by') or ir.get('result_limit') is not None:
            raise ValueError('Anti-join does not support sorting or pagination')
    projections = ir.get('projections', [])
    if not isinstance(projections, list) or len(projections) > 24:
        raise ValueError('Invalid projection list')
    for p in projections:
        prop(p)
        _alias(p['as'])
    if len({p['as'] for p in projections}) != len(projections):
        raise ValueError('Duplicate projection aliases')
    collisions = sorted({p['as'] for p in projections} & set(nodes))
    if collisions:
        raise ValueError('Projection aliases must differ from entity aliases: ' +
                         ', '.join(collisions))
    def filter_check(f, depth=0):
        if depth > 12 or not isinstance(f, dict):
            raise ValueError('Invalid or overly deep filter')
        op = f.get('op')
        if op in ('and', 'or'):
            children = f.get('children')
            if not isinstance(children, list) or not 2 <= len(children) <= 16:
                raise ValueError('Boolean group requires 2..16 children')
            for child in children: filter_check(child, depth+1)
        elif op == 'not':
            filter_check(f.get('child'), depth+1)
        elif op in ('eq', 'neq', 'contains', 'exists', 'not_exists'):
            if 'ignore_case' in f and (op != 'contains' or f['ignore_case'] is not True):
                raise ValueError('ignore_case is only supported for contains')
            prop(f)
            if op in ('eq', 'neq', 'contains'):
                _literal(f.get('value'))
        else:
            raise ValueError('Unsupported filter operator')
    if ir.get('filters') is not None:
        filter_check(ir['filters'])
    operation = ir.get('operation', {'type':'select'})
    if operation.get('type') not in ('select', 'count', 'group_count'):
        raise ValueError('Unsupported operation')
    if operation.get('type') == 'count' and projections:
        raise ValueError('COUNT currently requires no projections')
    if operation.get('type') == 'group_count':
        if len(projections) != 1:
            raise ValueError('Grouped COUNT requires exactly one SHACL-grounded group projection')
        threshold = operation.get('having_min')
        if threshold is not None and (type(threshold) is not int or not 0 <= threshold <= 1000000):
            raise ValueError('Invalid grouped count threshold')
    if not projections and operation.get('type') == 'select' and not ir.get('return_entities'):
        raise ValueError('SELECT needs projections or return_entities=true')
    # Optional LLM-authored SELECT modifiers. Never infer them from question text.
    ordering = ir.get('order_by', [])
    if not isinstance(ordering, list) or len(ordering) > 8:
        raise ValueError('order_by must be a list of at most eight sort terms')
    output_aliases = {p['as'] for p in projections}
    for term in ordering:
        if not isinstance(term, dict) or set(term) != {'as', 'direction'}:
            raise ValueError('Sort term must contain as and direction')
        if term['as'] not in output_aliases or term['direction'] not in ('asc', 'desc'):
            raise ValueError('Sort must reference a projected alias with asc/desc direction')
    result_limit = ir.get('result_limit')
    if result_limit is not None and (type(result_limit) is not int or not 1 <= result_limit <= 10000):
        raise ValueError('result_limit must be an integer from 1 to 10000')
    if operation.get('type') != 'select' and (ordering or result_limit is not None):
        raise ValueError('Sorting and pagination currently require SELECT')
    return ir


def compile_ir(ir, schema, *, mappings=None, graph_mode='all_named', graph_iri=None,
               include_graph=True, limit=100):
    """Validate and compile the unified IR into read-only SPARQL SELECT."""
    validate_ir(ir, schema, mappings=mappings)
    if graph_mode not in ('default', 'all_named', 'selected'):
        raise ValueError('Unsupported graph mode')
    if graph_mode == 'selected':
        graph_term = _iri(graph_iri)
    else:
        if graph_iri is not None:
            raise ValueError('graph_iri requires selected graph mode')
        graph_term = '?graph'
    if include_graph and graph_mode != 'all_named':
        raise ValueError('Graph provenance requires all_named')
    if not isinstance(limit, int) or not 1 <= limit <= 10000:
        raise ValueError('Invalid result limit')
    nodes = {n['alias']: n for n in ir['entities']}
    lines = []
    for e in ir.get('edges', []):
        l, r = '?'+e['from'], '?'+e['to']
        if e['kind'] == 'shacl':
            lines.append(f'{l} {_iri(e["predicate"])} {r} .')
        else:
            lines.append(f'{l} {_iri(e["left_predicate"])} ?key_{len(lines)} .')
            lines.append(f'{r} {_iri(e["right_predicate"])} ?otherkey_{len(lines)} .')
            # For mappings, lexical equivalence is explicit in the registry.
            a, b = f'?key_{len(lines)-2}', f'?otherkey_{len(lines)-1}'
            lines.append(f'FILTER(STR({a}) = STR({b}))')
    for p in ir.get('projections', []):
        lines.append(f'?{p["entity"]} {_iri(p["predicate"])} ?{p["as"]} .')
    if len(ir['entities']) == 1 and not lines:
        # Restrict the root to an actual SHACL-backed property, not arbitrary RDF triples.
        n = ir['entities'][0]
        shape_properties = [x for x in _schema_dict(schema)['shape_paths']
                            if x['domain'] == n['domain'] and x['node_shape'] == n['shape']]
        if not shape_properties:
            raise ValueError('Entity has no grounded property')
        lines.append(f'?{n["alias"]} {_iri(shape_properties[0]["path"])} ?_exists .')
    counter = [0]
    def filt(f):
        op = f['op']
        if op in ('and', 'or'):
            parts = [filt(c) for c in f['children']]
            if op == 'and': return '\n'.join(parts)
            return '{\n' + '\n} UNION {\n'.join(parts) + '\n}'
        if op == 'not':
            return 'FILTER NOT EXISTS {\n' + filt(f['child']) + '\n}'
        counter[0] += 1
        v = '?filter_' + str(counter[0])
        triple = f'?{f["entity"]} {_iri(f["predicate"])} {v} .'
        if op == 'exists': return 'FILTER EXISTS { ' + triple + ' }'
        if op == 'not_exists': return 'FILTER NOT EXISTS { ' + triple + ' }'
        literal = _literal(f['value'])
        expr = {'eq': f'isLiteral({v}) && STR({v}) = {literal}',
                'neq': f'isLiteral({v}) && STR({v}) != {literal}',
                'contains': f'isLiteral({v}) && CONTAINS(STR({v}), {literal})'}[op]
        return 'FILTER EXISTS { ' + triple + ' FILTER(' + expr + ') }'
    if ir.get('filters') is not None:
        lines.append(filt(ir['filters']))
    if not lines:
        raise ValueError('Empty graph pattern')
    body = '\n'.join('    ' + line for line in lines)
    if graph_mode != 'default':
        body = '  GRAPH ' + graph_term + ' {\n' + body + '\n  }'
    else:
        body = '\n'.join('  ' + line for line in lines)
    op = ir.get('operation', {'type':'select'})
    if op['type'] == 'count':
        if include_graph:
            return 'SELECT ?graph (COUNT(DISTINCT ?' + ir['entities'][0]['alias'] + ') AS ?count)\nWHERE {\n' + body + '\n}\nGROUP BY ?graph\nORDER BY ?graph'
        return 'SELECT (COUNT(DISTINCT ?' + ir['entities'][0]['alias'] + ') AS ?count)\nWHERE {\n' + body + '\n}'
    columns = (['?graph'] if include_graph else []) + ['?' + p['as'] for p in ir.get('projections', [])]
    if ir.get('return_entities'):
        columns += ['?' + n['alias'] for n in ir['entities']]
    if not columns:
        raise ValueError('No projected variables')
    cols = ' '.join(dict.fromkeys(columns))
    return f'SELECT DISTINCT {cols}\nWHERE {{\n{body}\n}}\nORDER BY {cols}\nLIMIT {limit}'

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Validate unified IR and compile read-only SPARQL')
    parser.add_argument('--ir', required=True, help='JSON file containing unified IR')
    parser.add_argument('--schema', required=True, help='DTwise schema index JSON')
    parser.add_argument('--mappings', help='Curated and independently verified mapping registry JSON')
    parser.add_argument('--graph-mode', choices=['default','all_named','selected'], default='all_named')
    parser.add_argument('--graph-iri')
    parser.add_argument('--no-graph', action='store_true')
    args = parser.parse_args()
    with open(args.ir, encoding='utf-8') as f: plan = json.load(f)
    registry = None
    if args.mappings:
        with open(args.mappings, encoding='utf-8') as f: registry = json.load(f)
    print(compile_ir(plan, args.schema, mappings=registry, graph_mode=args.graph_mode,
                     graph_iri=args.graph_iri, include_graph=not args.no_graph))
