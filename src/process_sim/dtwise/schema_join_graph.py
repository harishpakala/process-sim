"""Explicit, SHACL-evidence-checked multi-bridge identifier JOINs.

This is additive to existing two-key bridge and identifier-equality planners.
"""
import itertools
import re
from dtwise.query_planner import validate_hops
from dtwise.cross_domain_join import _mentioned, _words


def _explicit_bridge(domain, question):
    # Require bridge domain to appear after via/through, allowing lists of bridges.
    normalized = ' '.join(_words(question))
    match = re.search(r'\b(?:via|through)\b(.+?)(?:\busing\b|\bwith\b|[.;]|$)', normalized, re.I)
    return bool(match and _mentioned(domain, match.group(1)))


def _key_properties(candidate, label, schema):
    return [p for p in candidate['terminal'] if label in p['labels']
            and validate_hops([p['_hop']], schema, candidate['end'])]


def _connected(keysets):
    remaining = set(keysets)
    visited = {next(iter(remaining))}
    changed = True
    while changed:
        changed = False
        for domain in remaining - visited:
            if any(keysets[domain] & keysets[other] for other in visited):
                visited.add(domain)
                changed = True
    return visited == remaining


def plan_schema_join_graph(question, catalog, schema, domains):
    """Plan a multi-bridge graph with explicitly named domains, keys and bridges.

    Returns None when the request is not a multi-bridge request; raises on invalid
    multi-bridge requests so they cannot silently fall back to a weaker JOIN.
    """
    domains = sorted(set(domains))
    if len(domains) < 4:
        return None
    labels = sorted({label for c in catalog if c['domain'] in domains
                     for p in c['terminal'] for label in p['labels']
                     if isinstance(label, str) and not label.casefold().startswith('has')
                     and 'identifier' in ''.join(_words(label))
                     and _mentioned(label, question)})
    if len(labels) < 3:
        return None
    bridges = sorted(d for d in domains if _explicit_bridge(d, question))
    if len(bridges) < 2:
        return None
    if not re.search(r'\b(join|matching|shared|sharing|linked|via|through)\b', question, re.I):
        raise ValueError('Multi-bridge JOIN requires explicit linkage intent')
    missing = sorted(set(domains) - {c['domain'] for c in catalog})
    if missing:
        raise ValueError('Requested domains have no SHACL candidates: ' + ', '.join(missing))
    sides, keysets = [], {}
    for domain in domains:
        members = [c for c in catalog if c['domain'] == domain]
        names = {label for c in members for label in c['target_labels']}
        named = sorted(label for label in names if _mentioned(label, question))
        members = [c for c in members if not named or any(x in named for x in c['target_labels'])]
        options = []
        for c in members:
            if not validate_hops(c['_hops'], schema, c['root']):
                continue
            available = {label: _key_properties(c, label, schema) for label in labels}
            # A candidate endpoint must carry every key assigned to that endpoint.
            present = frozenset(label for label, props in available.items() if props)
            if not present:
                continue
            if domain in bridges:
                if len(present) < 2:
                    continue
            elif len(present) != 1:
                raise ValueError(f'Ambiguous external identifier assignment for {domain}')
            for combination in itertools.product(*(available[label] for label in sorted(present))):
                terminals = []
                for label, prop in zip(sorted(present), combination):
                    terminals.append({'label': label, 'predicate': prop['predicate'],
                                      'evidence_ids': list(prop['_hop']['evidence_ids'])})
                options.append({'root': c['root'], 'end_shape': c['end'],
                                'predicates': list(c['predicates']),
                                'evidence_ids': [e for hop in c['_hops'] for e in hop['evidence_ids']],
                                'terminals': terminals, 'target_labels': list(c['target_labels'])})
        if not options:
            raise ValueError(f'No verified multi-bridge endpoint for {domain}')
        distinct = {frozenset(t['label'] for t in branch['terminals']) for branch in options}
        if len(distinct) != 1:
            raise ValueError(f'Ambiguous identifier sets across endpoints for {domain}')
        keysets[domain] = next(iter(distinct))
        # Avoid duplicate alternative branches.
        unique = {}
        for branch in options:
            signature = (branch['root'], branch['end_shape'], tuple(branch['predicates']),
                         tuple((t['label'], t['predicate']) for t in branch['terminals']))
            unique[signature] = branch
        sides.append({'domain': domain, 'target_labels': named, 'branches': list(unique.values()),
                      'keys': sorted(keysets[domain])})
    if set().union(*keysets.values()) != set(labels):
        raise ValueError('Not all explicitly named identifiers are covered')
    if not _connected(keysets):
        raise ValueError('Requested identifier join graph is disconnected')
    for label in labels:
        if sum(label in keys for keys in keysets.values()) < 2:
            raise ValueError(f'Identifier {label} has no join partner')
    # Every explicitly designated bridge must actually connect >=2 keys.
    if any(len(keysets[domain]) < 2 for domain in bridges):
        raise ValueError('A designated bridge does not carry two identifiers')
    return {'query_type': 'SELECT', 'intent': 'list', 'join_type': 'schema_join_graph',
            'join_keys': labels, 'bridge_domains': bridges, 'sides': sides,
            'planner': 'shacl_explicit_multi_bridge_join_graph',
            'validation_scope': 'SHACL paths only; explicit domains, bridges and identifier labels'}


def compile_schema_join_graph(plan, schema, limit, graph_mode, graph_iri,
                              include_graph, count_per_graph, iri):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('Result limit must be 1..1000')
    if plan.get('join_type') != 'schema_join_graph' or plan.get('intent') != 'list':
        raise ValueError('Unsupported schema join graph')
    if count_per_graph or graph_iri is not None or graph_mode not in ('default', 'all_named'):
        raise ValueError('Unsupported graph options')
    if include_graph and graph_mode != 'all_named':
        raise ValueError('Graph provenance requires all_named mode')
    keys, sides, bridges = plan.get('join_keys'), plan.get('sides'), plan.get('bridge_domains')
    if (not isinstance(keys, list) or len(keys) < 3 or len(set(keys)) != len(keys)
            or not all(isinstance(k, str) and k for k in keys)
            or not isinstance(sides, list) or len(sides) < 4
            or not isinstance(bridges, list) or len(bridges) < 2 or len(set(bridges)) != len(bridges)):
        raise ValueError('Invalid multi-bridge topology')
    domains = [s.get('domain') for s in sides]
    if len(set(domains)) != len(domains) or not set(bridges) <= set(domains):
        raise ValueError('Invalid or duplicate domains')
    keysets, blocks = {}, []
    for i, side in enumerate(sides):
        domain = side['domain']
        branches = side.get('branches')
        if not isinstance(branches, list) or not branches:
            raise ValueError('Missing multi-bridge branches')
        patterns, sets = [], set()
        for j, branch in enumerate(branches):
            predicates, root, end = branch.get('predicates'), branch.get('root'), branch.get('end_shape')
            if not isinstance(predicates, list) or not predicates:
                raise ValueError('Empty structural path')
            valid = any(hops and hops[-1].get('to_shape') == end
                        and [h['property'] for h in hops] == predicates
                        and [e for h in hops for e in h['evidence_ids']] == branch.get('evidence_ids')
                        and validate_hops(hops, schema, root)
                        for hops in schema.shacl_paths(root, max_depth=len(predicates), domain=domain))
            if not valid:
                raise ValueError(f'Unverified structural path for {domain}')
            terminals = branch.get('terminals')
            if not isinstance(terminals, list) or not terminals:
                raise ValueError('Missing terminal identifier properties')
            terminal_labels = [t.get('label') for t in terminals]
            if len(set(terminal_labels)) != len(terminal_labels) or not set(terminal_labels) <= set(keys):
                raise ValueError('Invalid terminal identifier labels')
            for terminal in terminals:
                label, predicate, evidence = (terminal.get('label'), terminal.get('predicate'),
                                               terminal.get('evidence_ids'))
                concept = schema.by_uri.get(predicate, {})
                verified = (concept.get('domain') == domain and label in concept.get('labels', [])
                            and any(len(hops) == 1 and hops[0].get('to_shape') is None
                                    and hops[0].get('property') == predicate
                                    and hops[0].get('evidence_ids') == evidence
                                    and validate_hops(hops, schema, end)
                                    for hops in schema.shacl_paths(end, max_depth=1, domain=domain)))
                if not verified:
                    raise ValueError(f'Unverified terminal identifier {label} for {domain}')
            labelset = frozenset(terminal_labels)
            sets.add(labelset)
            if domain in bridges and len(labelset) < 2:
                raise ValueError('Bridge must bind two or more keys')
            if domain not in bridges and len(labelset) != 1:
                raise ValueError('External domain must bind exactly one key')
            variables = ([f'?root{i}_{j}'] + [f'?n{i}_{j}_{k}' for k in range(1, len(predicates))]
                         + [f'?entity{i}'])
            triples = [f'{variables[k]} {iri(predicate)} {variables[k+1]} .'
                       for k, predicate in enumerate(predicates)]
            triples.extend(f'?entity{i} {iri(t["predicate"])} ?joinKey{keys.index(t["label"])} .'
                           for t in terminals)
            patterns.append('{\n' + '\n'.join('    ' + t for t in triples) + '\n  }')
        if len(sets) != 1 or list(sets)[0] != frozenset(side.get('keys', [])):
            raise ValueError(f'Inconsistent branch key assignment for {domain}')
        keysets[domain] = next(iter(sets))
        inner = '\n  UNION\n  '.join(patterns)
        blocks.append(f'  GRAPH ?graph{i} {{\n  {inner}\n  }}' if graph_mode == 'all_named' else '  ' + inner)
    if not _connected(keysets) or set().union(*keysets.values()) != set(keys):
        raise ValueError('Disconnected or incomplete join graph')
    if any(sum(k in ks for ks in keysets.values()) < 2 for k in keys):
        raise ValueError('An identifier has no join partner')
    entities = [f'?entity{i}' for i in range(len(sides))]
    graphs = [f'?graph{i}' for i in range(len(sides))] if include_graph else []
    key_vars = [f'?joinKey{i}' for i in range(len(keys))]
    return ('SELECT DISTINCT ' + ' '.join(entities + key_vars + graphs) + '\nWHERE {\n'
            + '\n'.join(blocks) + '\n}\nORDER BY ' + ' '.join(key_vars + entities)
            + f'\nLIMIT {limit}')
