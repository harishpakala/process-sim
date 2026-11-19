"""Named-graph-aware compiler for validated unified IR 1.0 plans.

Each entity's triples are scoped independently, allowing joins across named graphs.
"""
from .unified_ir import validate_ir, _iri, _literal, _schema_dict, _alias


def compile_graph_ir(ir, schema, *, mappings=None, graph_mode='all_named', graph_iri=None,
                     include_graph=True, limit=None):
    validate_ir(ir, schema, mappings=mappings)
    if graph_mode not in ('default', 'all_named', 'selected'):
        raise ValueError('Unsupported graph mode')
    if graph_mode == 'selected':
        fixed = _iri(graph_iri)
    elif graph_iri is not None:
        raise ValueError('graph_iri requires selected graph mode')
    if include_graph and graph_mode != 'all_named':
        raise ValueError('Graph provenance requires all_named')
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 10000):
        raise ValueError('Invalid operational limit')
    domain_regex = ir.get('domain_regex')
    if domain_regex is not None:
        if include_graph:
            raise ValueError('Domain regex does not support graph provenance')
        import json
        clauses = []
        for shape, predicate in domain_regex['paths']:
            triple = f'?entity {_iri(predicate)} ?regex_value .'
            if graph_mode == 'all_named':
                triple = 'GRAPH ?regex_graph { ' + triple + ' }'
            elif graph_mode == 'selected':
                triple = 'GRAPH ' + fixed + ' { ' + triple + ' }'
            clauses.append('{ ' + triple + ' }')
        # All shape owners are included; UNION is a set of evidenced
        # property patterns, not an inferred rdf:type assertion.
        pattern = json.dumps(domain_regex['pattern'], ensure_ascii=True)
        query = ('SELECT DISTINCT ?entity\nWHERE {\n  '
                 + '\n  UNION\n  '.join(clauses)
                 + '\n  FILTER(isLiteral(?regex_value) && '
                 + 'REGEX(STR(?regex_value), ' + pattern + '))\n}')
        return query
    nodes = {n['alias']: n for n in ir['entities']}
    # Every triple is scoped to the graph of its SUBJECT entity. Distinct entity
    # aliases may bind to different graphs, even within one domain.
    def scoped(alias, body):
        if graph_mode == 'default':
            return body
        graph = fixed if graph_mode == 'selected' else '?graph_' + alias
        return 'GRAPH ' + graph + ' { ' + body + ' }'
    anti = ir.get('anti_join')
    if anti is not None:
        if graph_mode != 'all_named' or include_graph:
            raise ValueError('Anti-join requires all_named graphs without graph provenance')
        edge = ir['edges'][0]  # validate_ir verifies this exact mapping edge.
        source, target = anti['from'], anti['to']
        left = scoped(source, f'?{source} {_iri(edge["left_predicate"])} ?anti_key .')
        right = scoped(target, f'?{target} {_iri(edge["right_predicate"])} ?anti_other .')
        return ('SELECT DISTINCT ?' + source + '\nWHERE {\n'
                + '  ' + left + '\n'
                + '  FILTER NOT EXISTS { ' + right
                + ' FILTER(STR(?anti_key) = STR(?anti_other)) }\n}')
    parts = []
    anchor = set()
    for i, e in enumerate(ir.get('edges', [])):
        a, b = e['from'], e['to']
        if e['kind'] == 'shacl':
            parts.append(scoped(a, f'?{a} {_iri(e["predicate"])} ?{b} .'))
            anchor.add(a); anchor.add(b)
        else:
            x, y = f'?join_{i}_left', f'?join_{i}_right'
            parts.append(scoped(a, f'?{a} {_iri(e["left_predicate"])} {x} .'))
            parts.append(scoped(b, f'?{b} {_iri(e["right_predicate"])} {y} .'))
            parts.append(f'FILTER(STR({x}) = STR({y}))')
            anchor.add(a); anchor.add(b)
    for p in ir.get('projections', []):
        parts.append(scoped(p['entity'], f'?{p["entity"]} {_iri(p["predicate"])} ?{p["as"]} .'))
        anchor.add(p['entity'])
    # Positive conjunctive property conditions can ground an otherwise unbound
    # entity. This is essential for COUNT with an EXISTS condition: choosing the
    # first unrelated schema property would silently undercount.
    def positive_anchors(f):
        if not isinstance(f, dict):
            return []
        if f.get('op') == 'and':
            return [leaf for child in f['children'] for leaf in positive_anchors(child)]
        if f.get('op') in ('exists', 'eq', 'neq', 'contains'):
            return [f]
        return []  # OR, NOT, NOT EXISTS cannot safely anchor an entity.

    available = positive_anchors(ir.get('filters'))
    for a, n in nodes.items():
        if a not in anchor:
            matching = next((f for f in available if f['entity'] == a), None)
            if matching:
                # Bind both the entity and its named graph in the outer WHERE.
                # The validated filter below still applies its actual condition.
                parts.append(scoped(a, f'?{a} {_iri(matching["predicate"])} ?anchor_{a} .'))
            else:
                candidates = [x for x in _schema_dict(schema)['shape_paths'] if
                              x['domain'] == n['domain'] and x['node_shape'] == n['shape']
                              and x.get('evidence')]
                if not candidates:
                    raise ValueError('Entity has no evidenced SHACL anchor: ' + a)
                parts.append(scoped(a, f'?{a} {_iri(candidates[0]["path"])} ?anchor_{a} .'))
    count = [0]
    def filt(f):
        op = f['op']
        if op in ('and', 'or'):
            clauses = [filt(x) for x in f['children']]
            if op == 'and': return '\n'.join(clauses)
            return '{ ' + ' } UNION { '.join(clauses) + ' }'
        if op == 'not':
            return 'FILTER NOT EXISTS { ' + filt(f['child']) + ' }'
        count[0] += 1
        v = '?filter_' + str(count[0])
        triple = scoped(f['entity'], f'?{f["entity"]} {_iri(f["predicate"])} {v} .')
        if op == 'exists': return 'FILTER EXISTS { ' + triple + ' }'
        if op == 'not_exists': return 'FILTER NOT EXISTS { ' + triple + ' }'
        lit = _literal(f['value'])
        if op == 'contains' and f.get('ignore_case') is True:
            return ('FILTER EXISTS { ' + triple + ' FILTER(isLiteral(' + v
                    + ') && CONTAINS(LCASE(STR(' + v + ')), LCASE(' + lit + '))) }')
        expr = {'eq': f'isLiteral({v}) && STR({v}) = {lit}',
                'neq': f'isLiteral({v}) && STR({v}) != {lit}',
                'contains': f'isLiteral({v}) && CONTAINS(STR({v}), {lit})'}[op]
        return 'FILTER EXISTS { ' + triple + ' FILTER(' + expr + ') }'
    if ir.get('filters') is not None:
        parts.append(filt(ir['filters']))
    body = '\n'.join('  ' + x for x in parts)
    graphs = ['?graph_' + n['alias'] for n in ir['entities']] if include_graph else []
    op = ir.get('operation', {'type': 'select'})
    if op['type'] == 'count':
        root = '?' + ir['entities'][0]['alias']
        select = 'SELECT ' + ' '.join(graphs) + f' (COUNT(DISTINCT {root}) AS ?count)'
        group = ('\nGROUP BY ' + ' '.join(graphs)) if graphs else ''
        return select + '\nWHERE {\n' + body + '\n}' + group
    if op['type'] == 'group_count':
        group_var = '?' + ir['projections'][0]['as']
        root = '?' + ir['entities'][0]['alias']
        # Group by the requested SHACL property, never by graph provenance.
        # DISTINCT protects against duplicated evidence triples across graphs.
        query = (f'SELECT {group_var} (COUNT(DISTINCT {root}) AS ?count)'
                 + '\nWHERE {\n' + body + '\n}'
                 + '\nGROUP BY ' + group_var)
        threshold = op.get('having_min')
        if threshold is not None:
            query += f'\nHAVING(COUNT(DISTINCT {root}) > {threshold})'
        return query
    cols = graphs + ['?' + p['as'] for p in ir.get('projections', [])]
    if ir.get('return_entities'):
        cols += ['?' + n['alias'] for n in ir['entities']]
    cols = list(dict.fromkeys(cols))
    order_terms = ir.get('order_by', [])
    query = 'SELECT DISTINCT ' + ' '.join(cols) + '\nWHERE {\n' + body + '\n}'
    if order_terms:
        ordering = ' '.join(('ASC' if term['direction'] == 'asc' else 'DESC') +
                            '(?' + term['as'] + ')' for term in order_terms)
        query += '\nORDER BY ' + ordering
    requested_limit = ir.get('result_limit')
    if requested_limit is not None:
        if limit is not None and requested_limit > limit:
            raise ValueError('Requested result limit exceeds operational cap; '
                             'do not silently truncate the semantic query')
        query += f'\nLIMIT {requested_limit}'
    return query
