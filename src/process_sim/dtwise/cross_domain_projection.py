"""Conservative SHACL-grounded cross-domain terminal-property projection/filter joins.

No ontology-specific class, domain, predicate or identifier is embedded here.
"""
import json
import re
from process_sim.dtwise.query_planner import validate_hops


def _words(value):
    value = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', str(value))
    return tuple(re.findall(r'[a-z0-9]+', value.casefold()))


def _same(label, requested):
    words = _words(label)
    asked = _words(requested)
    def singular(parts):
        return parts[:-1] + ((parts[-1][:-1] if parts[-1].endswith('s') and not parts[-1].endswith('ss') else parts[-1]),) if parts else parts
    return singular(words) == singular(asked) or (words[:1] == ('has',) and singular(words[1:]) == singular(asked))


def _properties(candidate, requested, schema):
    return [p for p in candidate['terminal']
            if any(_same(label, requested) for label in p['labels'] + [p['predicate'].rsplit('/', 1)[-1]])
            and validate_hops([p['_hop']], schema, candidate['end'])]


def _entity_matches(candidate, requested):
    return any(_same(label, requested) for label in candidate['target_labels'])


def plan_cross_domain_projection(question, catalog, schema):
    """Only parse unambiguous 'Get OUTPUT of the DOMAIN ENTITY with FILTER VALUE'.

    Shared identifier *labels* provide a candidate equality key, not an RDF edge.
    The caller must separately decide whether equality semantics are authorized.
    """
    match = re.fullmatch(
        r'\s*(?:get|show|list|retrieve|return|find)\s+(?:the\s+)?'
        r'(?P<output>[A-Za-z][A-Za-z0-9_ ]*?)\s+of\s+(?:the\s+|an?\s+)?'
        r'(?P<domain>[A-Za-z][A-Za-z0-9_]*)\s+'
        r'(?P<entity>[A-Za-z][A-Za-z0-9_]*)\s+'
        r'(?:with|where)\s+(?P<filter>[A-Za-z][A-Za-z0-9_ ]*?)\s+'
        r'(?P<value>[A-Za-z0-9][A-Za-z0-9_.:-]*)\s*[.!?]?\s*', question, re.I)
    matched_by = None
    if not match:
        matched_by = re.fullmatch(
            r'\s*(?:get|show|list|retrieve|return|find)\s+(?:the\s+)?'
            r'(?P<output>[A-Za-z][A-Za-z0-9_ ]*?)\s+'
            r'for\s+(?:the\s+)?'
            r'(?P<domain>[A-Za-z][A-Za-z0-9_]*)\s+'
            r'(?P<entity>[A-Za-z][A-Za-z0-9_]*)\s+'
            r'matched\s+by\s+(?P<join>[A-Za-z][A-Za-z0-9_ ]*?)\s*[.!?]?\s*',
            question, re.I)
    unfiltered = None
    if not match and not matched_by:
        unfiltered = re.fullmatch(
            r'\s*(?:find|list|show|retrieve|return|get)\s+(?:the\s+)?'
            r'(?P<output>[A-Za-z][A-Za-z0-9_ ]*?)\s+'
            r'associated\s+with\s+(?:the\s+)?'
            r'(?P<domain>[A-Za-z][A-Za-z0-9_]*)\s+'
            r'(?P<entity>[A-Za-z][A-Za-z0-9_]*)\s+'
            r'through\s+(?P<join>[A-Za-z][A-Za-z0-9_ ]*?)\s*[.!?]?\s*',
            question, re.I)
        if not unfiltered:
            return None
    request = match or unfiltered or matched_by
    domain = request.group('domain')
    domains = {c['domain'] for c in catalog}
    if not any(_same(d, domain) for d in domains):
        return None
    source = []
    for c in catalog:
        if not _same(c['domain'], domain) or not _entity_matches(c, request.group('entity')):
            continue
        filters = _properties(c, match.group('filter'), schema) if match else [None]
        if len(filters) == 1 and validate_hops(c['_hops'], schema, c['root']):
            source.append((c, filters[0]))
    targets = []
    for c in catalog:
        if _same(c['domain'], domain):
            continue
        outputs = _properties(c, request.group('output'), schema)
        if len(outputs) == 1 and validate_hops(c['_hops'], schema, c['root']):
            targets.append((c, outputs[0]))
    if not source or not targets:
        return None
    choices = []
    for sc, fp in source:
        for tc, op in targets:
            skeys = {tuple(_words(label)): p for p in sc['terminal']
                     for label in p['labels'] if _words(label)[-1:] == ('identifier',)
                     and validate_hops([p['_hop']], schema, sc['end'])}
            tkeys = {tuple(_words(label)): p for p in tc['terminal']
                     for label in p['labels'] if _words(label)[-1:] == ('identifier',)
                     and validate_hops([p['_hop']], schema, tc['end'])}
            for key in skeys.keys() & tkeys.keys():
                if (match and key == _words(match.group('filter'))) or key == _words(request.group('output')):
                    continue
                if (unfiltered or matched_by) and key != _words(request.group('join')):
                    continue
                choices.append((sc, fp, skeys[key], tc, op, tkeys[key], key))
    # Deduplicate equivalent path signatures, but do not guess among distinct paths.
    unique = {}
    for choice in choices:
        sc, fp, sk, tc, op, tk, key = choice
        signature = (sc['root'], tuple(sc['predicates']), sc['end'], fp['predicate'] if fp else None,
                     sk['predicate'], tc['root'], tuple(tc['predicates']), tc['end'],
                     op['predicate'], tk['predicate'])
        unique[signature] = choice
    if len(unique) != 1:
        raise ValueError('Cross-domain projection requires one unambiguous SHACL-validated join path; found %d' % len(unique))
    sc, fp, sk, tc, op, tk, key = next(iter(unique.values()))
    def branch(c, keyprop):
        return {'domain': c['domain'], 'root': c['root'], 'end_shape': c['end'],
                'predicates': list(c['predicates']),
                'evidence_ids': [e for hop in c['_hops'] for e in hop['evidence_ids']],
                'key_predicate': keyprop['predicate'],
                'key_evidence_ids': list(keyprop['_hop']['evidence_ids'])}
    return {'query_type': 'SELECT', 'intent': 'list', 'join_type': 'cross_domain_projection',
            'planner': 'shacl_cross_domain_projection', 'join_key_label': ' '.join(key),
            'source': branch(sc, sk), 'target': branch(tc, tk),
            'filter': ({'predicate': fp['predicate'], 'evidence_ids': list(fp['_hop']['evidence_ids']),
                       'value': match.group('value').rstrip('.!?')} if fp else None),
            'projection': {'predicate': op['predicate'], 'evidence_ids': list(op['_hop']['evidence_ids'])},
            'validation_scope': 'SHACL paths and common identifier label; equality semantics require independent authorization'}


def compile_cross_domain_projection(plan, schema, limit, graph_mode, graph_iri,
                                    include_graph, count_per_graph, iri):
    if plan.get('join_type') != 'cross_domain_projection' or plan.get('intent') != 'list' or plan.get('query_type') != 'SELECT':
        raise ValueError('Unsupported cross-domain projection plan')
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('Result limit must be 1..1000')
    if graph_mode not in ('default', 'all_named') or graph_iri is not None or count_per_graph:
        raise ValueError('Unsupported graph options for cross-domain projection')
    if include_graph and graph_mode != 'all_named':
        raise ValueError('Graph provenance requires all_named')
    def validate_terminal(branch, predicate, evidence):
        return any(len(hops) == 1 and hops[0].get('to_shape') is None
                   and hops[0]['property'] == predicate and hops[0]['evidence_ids'] == evidence
                   and validate_hops(hops, schema, branch['end_shape'])
                   for hops in schema.shacl_paths(branch['end_shape'], max_depth=1, domain=branch['domain']))
    # New structured plans can contain zero or more source/target filters.
    # Legacy plans retain their single source-side `filter` contract.
    filters = plan.get('filters')
    if filters is None:
        legacy = plan.get('filter')
        filters = ([dict(legacy, domain=plan['source']['domain'], operator='eq')]
                   if legacy is not None else [])
    if not isinstance(filters, list):
        raise ValueError('Invalid cross-domain filters')
    blocks = []
    filter_expressions = []
    for index, role in enumerate(('source', 'target')):
        branch = plan[role]
        predicates = branch['predicates']
        if not predicates or not any(hops and hops[-1].get('to_shape') == branch['end_shape']
                and [h['property'] for h in hops] == predicates
                and [e for h in hops for e in h['evidence_ids']] == branch['evidence_ids']
                and validate_hops(hops, schema, branch['root'])
                for hops in schema.shacl_paths(branch['root'], max_depth=len(predicates), domain=branch['domain'])):
            raise ValueError('Cross-domain traversal lacks SHACL evidence')
        if not validate_terminal(branch, branch['key_predicate'], branch['key_evidence_ids']):
            raise ValueError('Join identifier lacks SHACL evidence')
        if role == 'target' and not validate_terminal(branch, plan['projection']['predicate'],
                                                       plan['projection']['evidence_ids']):
            raise ValueError('Cross-domain output lacks SHACL evidence')
        nodes = [f'?root{index}'] + [f'?node{index}_{i}' for i in range(1, len(predicates))] + [f'?entity{index}']
        triples = [f'{nodes[i]} {iri(predicate)} {nodes[i+1]} .' for i, predicate in enumerate(predicates)]
        triples.append(f'{nodes[-1]} {iri(branch["key_predicate"])} ?joinKey .')
        if role == 'target':
            triples.append(f'{nodes[-1]} {iri(plan["projection"]["predicate"])} ?value .')
        for j, spec in enumerate(filters):
            if not isinstance(spec, dict) or spec.get('operator') != 'eq':
                raise ValueError('Unsupported cross-domain filter')
            if spec.get('domain') not in (plan['source']['domain'], plan['target']['domain']):
                raise ValueError('Filter domain is not part of join')
            if spec['domain'] != branch['domain']:
                continue
            if not validate_terminal(branch, spec.get('predicate'), spec.get('evidence_ids')):
                raise ValueError('Cross-domain filter lacks SHACL evidence')
            value = spec.get('value')
            if not isinstance(value, str) or not 1 <= len(value) <= 200 or any(ord(c) < 32 for c in value):
                raise ValueError('Invalid filter literal')
            variable = f'?filterValue{j}'
            triples.append(f'{nodes[-1]} {iri(spec["predicate"])} {variable} .')
            filter_expressions.append('  FILTER(STR(' + variable + ') = ' + json.dumps(value, ensure_ascii=True) + ')')
        block = '\n'.join('    ' + triple for triple in triples)
        if graph_mode == 'all_named':
            block = f'  GRAPH ?graph{index} {{\n{block}\n  }}'
        blocks.append(block)
    blocks.extend(filter_expressions)
    cols = '?value' + (' ?graph0 ?graph1' if include_graph else '')
    return (f'SELECT DISTINCT {cols}\nWHERE {{\n' + '\n'.join(blocks)
            + f'\n}}\nORDER BY ?value\nLIMIT {limit}')
