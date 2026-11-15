"""Evidence-checked N-domain identifier equality joins; no inferred RDF edges."""
import re
from process_sim.dtwise.query_planner import validate_hops

def _words(text):
    text = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', str(text))
    words = re.findall(r'[a-z0-9]+', text.lower())
    return [w[:-3]+'y' if w.endswith('ies') and len(w)>3 else w[:-1] if w.endswith('s') and len(w)>2 and not w.endswith('ss') else w for w in words]


def _mentioned(label, question):
    """Match schema labels in compact or separated spelling, on word boundaries.

    Schema domain `assetinventory` must match `AssetInventory` or
    `asset inventory`, without matching an arbitrary substring of a word.
    """
    a, b = _words(label), _words(question)
    if not a:
        return False
    target = ''.join(a)
    return any(''.join(b[i:j]) == target
               for i in range(len(b))
               for j in range(i + 1, min(len(b), i + len(target)) + 1))


def _join_candidates(question, catalog, schema):

    # Identify requested domains using the complete schema,
    # not only domains that survived candidate discovery.
    schema_domains = sorted({
        str(c["domain"])
        for c in schema.concepts
        if c.get("domain")
    })
    
    requested_domains = sorted({
        domain
        for domain in schema_domains
        if _mentioned(domain, question)
    })
    
    # Candidate discovery must support every requested domain.
    candidate_domains = {
        c["domain"] for c in catalog
    }
    
    missing_domains = sorted(
        set(requested_domains) - candidate_domains
    )
    
    if missing_domains:
        raise ValueError(
            "Requested domains have no SHACL-validated query candidates: "
            + ", ".join(missing_domains)
        )
    
    domains = requested_domains
    
    if len(domains) < 2:
        return None
    if not re.search(r'\b(same|matching|equal|identical|sharing|shared)\b', question, re.I):
        raise ValueError('Multiple domains require an explicit identifier equality request')
    # Explicit entity labels constrain a side; an unnamed side retains every
    # schema-verified endpoint with the requested shared terminal property.
    # No instance-data heuristics or domain-specific class lists are used.
    groups = []
    for domain in domains:
        members = [c for c in catalog if c['domain'] == domain]
        labels = {label for c in members for label in c['target_labels']}
        named = {label for label in labels if _mentioned(label, question)}
        matches = [c for c in members if not named or any(
            label in named for label in c['target_labels'])]
        groups.append((domain, sorted(named), matches))
    # Require a unique identifier property explicitly named in the question.
    keys = {}
    for domain, named, matches in groups:
        properties = {label for c in matches for p in c['terminal']
                      for label in p['labels']
                      if not label.casefold().startswith('has')
                      and _mentioned(label, question)}
        keys[domain] = properties
    common = set.intersection(*(keys[d] for d, _, _ in groups))
    if len(common) != 1:
        raise ValueError('No unique explicitly named shared terminal identifier property')
    key = next(iter(common))
    sides = []
    for domain, named, matches in groups:
        branches = []
        seen = set()
        for c in matches:
            if not validate_hops(c['_hops'], schema, c['root']):
                continue
            for prop in c['terminal']:
                if key not in prop['labels']:
                    continue
                if not validate_hops([prop['_hop']], schema, c['end']):
                    continue
                signature = (c['root'], c['end'], tuple(c['predicates']), prop['predicate'])
                if signature in seen:
                    continue
                seen.add(signature)
                branches.append({'root': c['root'], 'end_shape': c['end'],
                                 'predicates': c['predicates'],
                                 'evidence_ids': [e for h in c['_hops'] for e in h['evidence_ids']],
                                 'key_predicate': prop['predicate'],
                                 'key_evidence_ids': prop['_hop']['evidence_ids'],
                                 'target_labels': c['target_labels']})
        if not branches:
            raise ValueError(f'No verified identifier path for {domain}: {named or "broad scope"}')
        sides.append({'domain': domain, 'target_labels': named, 'branches': branches})
    return {'query_type': 'SELECT', 'intent': 'list', 'join_type': 'identifier_equality',
            'key_label': key, 'sides': sides, 'planner': 'shacl_n_domain_identifier_join',
            'validation_scope': 'SHACL paths only; identifier semantics authorized by caller'}


def _generic_bridge_candidates(question, catalog, schema, domains):
    """Discover an explicitly requested two-key star bridge from SHACL paths.

    No domain, identifier label, or RDF predicate is hardcoded. Every non-bridge
    domain must have exactly one of the two named keys; ambiguity fails closed.
    """
    # The spelling of a schema domain may be compact or CamelCase.
    normalized_question = ' '.join(_words(question))
    
    normalized_question = ' '.join(_words(question))
    
    def bridge_mentioned_after_via(domain):
        # Accept the compact domain spelling in the original question.
        compact = re.search(
            r'\b(?:via|through)\s+' + re.escape(domain) + r'\b',
            question,
            re.I
        )
    
        # Accept the normalized domain spelling.
        spaced = re.search(
            r'\b(?:via|through)\s+'
            + r'\s+'.join(map(re.escape, _words(domain)))
            + r'\b',
            normalized_question,
            re.I
        )
    
        return bool(compact or spaced)
    
    via = [d for d in domains if bridge_mentioned_after_via(d)]
    if len(via) != 1:
        raise ValueError('Generic bridge JOIN requires exactly one explicit via/through domain')
    bridge_domain = via[0]
    if not re.search(r'\b(same|matching|equal|identical|sharing|shared|join|linked|via|through)\b', question, re.I):
        raise ValueError('Bridge JOIN requires explicit linkage intent')
    groups = {}
    for domain in domains:
        members = [c for c in catalog if c['domain'] == domain]
        names = {label for c in members for label in c['target_labels']}
        named = {label for label in names if _mentioned(label, question)}
        groups[domain] = (sorted(named), [c for c in members if not named or
                          any(label in named for label in c['target_labels'])])
    # Only identifier-labelled terminal properties named in the question qualify.
    labels = sorted({label for d in domains for c in groups[d][1]
                     for p in c['terminal'] for label in p['labels']
                     if not str(label).casefold().startswith('has')
                     and _mentioned(label, question)
                     and 'identifier' in ''.join(_words(label))})
    if len(labels) != 2:
        raise ValueError('Generic bridge requires exactly two explicitly named identifier properties')
    bridge, other = labels
    # The bridge entity must carry both keys on one and the same SHACL endpoint.
    def properties(c, label):
        return [p for p in c['terminal'] if label in p['labels']
                and validate_hops([p['_hop']], schema, c['end'])]
    sides = []
    assignments = {}
    for domain in domains:
        named, members = groups[domain]
        branches, seen = [], set()
        for c in members:
            if not validate_hops(c['_hops'], schema, c['root']):
                continue
            available = {label: properties(c, label) for label in labels}
            if domain == bridge_domain:
                pairs = [(a, b) for a in available[bridge] for b in available[other]]
                options = [(bridge, a, other, b) for a, b in pairs]
            else:
                options = [(label, p, None, None) for label in labels
                           for p in available[label]]
            for key_label, prop, second_label, second in options:
                signature = (c['root'], c['end'], tuple(c['predicates']),
                             prop['predicate'], second['predicate'] if second else None)
                if signature in seen:
                    continue
                seen.add(signature)
                branch = {
                    'root': c['root'], 'end_shape': c['end'],
                    'predicates': list(c['predicates']),
                    'evidence_ids': [e for h in c['_hops'] for e in h['evidence_ids']],
                    'key_label': key_label, 'key_predicate': prop['predicate'],
                    'key_evidence_ids': list(prop['_hop']['evidence_ids']),
                    'target_labels': c['target_labels'],
                }
                if second:
                    branch.update({'bridge_key_label': second_label,
                                   'bridge_predicate': second['predicate'],
                                   'bridge_evidence_ids': list(second['_hop']['evidence_ids'])})
                branches.append(branch)
        if not branches:
            raise ValueError(f'No verified bridge path for {domain}')
        if domain != bridge_domain:
            possible = {b['key_label'] for b in branches}
            if len(possible) != 1:
                raise ValueError(f'Ambiguous identifier assignment for {domain}: {sorted(possible)}')
            assignments[domain] = next(iter(possible))
        sides.append({'domain': domain, 'target_labels': named, 'branches': branches})
    if set(assignments.values()) != set(labels):
        raise ValueError('Both bridge identifier groups must have an external domain')
    return {'query_type': 'SELECT', 'intent': 'list',
            'join_type': 'schema_bridge_join', 'join_keys': labels,
            'bridge_domain': bridge_domain, 'sides': sides,
            'planner': 'shacl_generic_two_key_bridge_join',
            'validation_scope': 'SHACL paths only; bridge and both identifiers explicitly named'}


def plan_join(question, catalog, schema):
    schema_domains = sorted({str(c['domain']) for c in schema.concepts if c.get('domain')})
    domains = sorted(d for d in schema_domains if _mentioned(d, question))
    from process_sim.dtwise.schema_join_graph import plan_schema_join_graph
    graph_plan = plan_schema_join_graph(question, catalog, schema, domains)
    if graph_plan is not None:
        return graph_plan
    if ('productcatalog' in domains and 'assetinventory' in domains and len(domains) >= 3
            and not any(re.search(r'\b(?:via|through)\s+'
                                  + r'\s*'.join(map(re.escape, _words(d))) + r'\b',
                                  ' '.join(_words(question)), re.I)
                        for d in domains if d != 'assetinventory')):
        # Do not silently reinterpret a same-AssetIdentifier question.
        if _mentioned('ProductIdentifier', question):
            missing = sorted(set(domains) - {c['domain'] for c in catalog})
            if missing:
                raise ValueError('Requested domains have no SHACL-validated query candidates: '
                                 + ', '.join(missing))
            return _bridge_candidates(question, catalog, schema, domains)
    if len(domains) >= 3 and re.search(r'\b(?:via|through)\b', question, re.I):
        missing = sorted(set(domains) - {c['domain'] for c in catalog})
        if missing:
            raise ValueError('Requested domains have no SHACL-validated query candidates: '
                             + ', '.join(missing))
        return _generic_bridge_candidates(question, catalog, schema, domains)
    return _join_candidates(question, catalog, schema)


def compile_join(plan, schema, limit, graph_mode, graph_iri, include_graph, count_per_graph, iri):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('Result limit must be 1..1000')
    if plan.get('join_type') != 'identifier_equality' or plan.get('intent') != 'list':
        raise ValueError('Unsupported cross-domain join')
    if count_per_graph:
        raise ValueError('Per-graph counts are not supported for cross-domain joins')
    if graph_mode == 'selected':
        raise ValueError('Cross-domain joins require independent graphs; selected single graph is unsupported')
    if graph_iri is not None:
        raise ValueError('graph_iri is not supported for cross-domain joins')
    if graph_mode not in ('default', 'all_named'):
        raise ValueError('Unsupported graph mode')
    sides = plan.get('sides')
    if (not isinstance(sides, list) or len(sides) < 2 or
            len({side.get('domain') for side in sides}) != len(sides)):
        raise ValueError('At least two distinct domain sides required')
    if include_graph and graph_mode != 'all_named':
        raise ValueError('Graph provenance requires all_named mode')
    blocks = []
    for side_idx, side in enumerate(sides):
        domain, branches = side['domain'], side.get('branches')
        if not isinstance(branches, list) or not branches:
            raise ValueError('Join side lacks branches')
        patterns = []
        for branch_idx, branch in enumerate(branches):
            predicates = branch['predicates']
            if not predicates:
                raise ValueError('Empty structural path')
            root, end = branch['root'], branch['end_shape']
            valid = any(hops[-1].get('to_shape') == end and
                        [h['property'] for h in hops] == predicates and
                        [e for h in hops for e in h['evidence_ids']] == branch['evidence_ids'] and
                        validate_hops(hops, schema, root)
                        for hops in schema.shacl_paths(root, max_depth=len(predicates), domain=domain))
            terminal = any(len(hops) == 1 and hops[0]['to_shape'] is None and
                           hops[0]['property'] == branch['key_predicate'] and
                           hops[0]['evidence_ids'] == branch['key_evidence_ids'] and
                           validate_hops(hops, schema, end)
                           for hops in schema.shacl_paths(end, max_depth=1, domain=domain))
            key_concept = schema.by_uri.get(branch['key_predicate'], {})
            if (not valid or not terminal or key_concept.get('domain') != domain or
                    plan['key_label'] not in key_concept.get('labels', [])):
                raise ValueError('Cross-domain join lacks verified SHACL evidence')
            variables = [f'?root{side_idx}_{branch_idx}'] + [f'?n{side_idx}_{branch_idx}_{i}' for i in range(1,len(predicates))] + [f'?entity{side_idx}']
            triples = [f'{variables[i]} {iri(p)} {variables[i+1]} .' for i,p in enumerate(predicates)]
            triples.append(f'?entity{side_idx} {iri(branch["key_predicate"])} ?assetId .')
            patterns.append('{\n' + '\n'.join('    '+t for t in triples) + '\n  }')
        inner = '\n  UNION\n  '.join(patterns)
        if graph_mode == 'all_named':
            blocks.append(f'  GRAPH ?graph{side_idx} {{\n  {inner}\n  }}')
        else:
            blocks.append('  '+inner)
    entity_vars = [f'?entity{i}' for i in range(len(sides))]
    graph_vars = [f'?graph{i}' for i in range(len(sides))]
    projections = ' '.join(entity_vars + ['?assetId'] + (graph_vars if include_graph else []))
    order = ' '.join(['?assetId'] + entity_vars)
    return (f'SELECT DISTINCT {projections}\nWHERE {{\n' + '\n'.join(blocks) +
            f'\n}}\nORDER BY {order}\nLIMIT {limit}')


# The bridge is authorized only when the question explicitly names both keys
# and the bridge domain. All predicates are discovered from SHACL candidates.
def _bridge_candidates(question, catalog, schema, domains):
    bridge_domain = 'assetinventory'
    product_domain = 'productcatalog'
    asset_key = 'AssetIdentifier'
    product_key = 'ProductIdentifier'
    if bridge_domain not in domains or product_domain not in domains:
        return None
    if not (_mentioned(asset_key, question) and _mentioned(product_key, question)
            and _mentioned(bridge_domain, question)):
        return None
    if not re.search(r'\b(same|matching|equal|identical|sharing|shared|join|linked|via|through)\b', question, re.I):
        raise ValueError('Bridge JOIN requires explicit equality or linkage intent')

    sides = []
    for domain in domains:
        key = product_key if domain == product_domain else asset_key
        members = [c for c in catalog if c['domain'] == domain]
        labels = {label for c in members for label in c['target_labels']}
        named = {label for label in labels if _mentioned(label, question)}
        matches = [c for c in members if not named or any(
            label in named for label in c['target_labels'])]
        branches = []
        seen = set()
        for c in matches:
            if not validate_hops(c['_hops'], schema, c['root']):
                continue
            props = [p for p in c['terminal'] if key in p['labels']
                     and validate_hops([p['_hop']], schema, c['end'])]
            extra = []
            if domain == bridge_domain:
                extra = [p for p in c['terminal'] if product_key in p['labels']
                         and validate_hops([p['_hop']], schema, c['end'])]
                if not extra:
                    continue
            for prop in props:
                for other in (extra if domain == bridge_domain else [None]):
                    signature = (c['root'], c['end'], tuple(c['predicates']),
                                 prop['predicate'], other['predicate'] if other else None)
                    if signature in seen:
                        continue
                    seen.add(signature)
                    branch = {
                        'root': c['root'], 'end_shape': c['end'],
                        'predicates': list(c['predicates']),
                        'evidence_ids': [e for h in c['_hops'] for e in h['evidence_ids']],
                        'key_predicate': prop['predicate'],
                        'key_evidence_ids': list(prop['_hop']['evidence_ids']),
                        'target_labels': c['target_labels'],
                    }
                    if other:
                        branch['bridge_predicate'] = other['predicate']
                        branch['bridge_evidence_ids'] = list(other['_hop']['evidence_ids'])
                    branches.append(branch)
        if not branches:
            raise ValueError(f'No verified bridge identifier path for {domain}: {sorted(named) or "broad scope"}')
        sides.append({'domain': domain, 'target_labels': sorted(named), 'branches': branches})
    return {
        'query_type': 'SELECT', 'intent': 'list',
        'join_type': 'multi_key_bridge_join',
        'key_label': asset_key, 'product_key_label': product_key,
        'bridge_domain': bridge_domain, 'product_domain': product_domain,
        'sides': sides, 'planner': 'shacl_multi_key_bridge_join',
        'validation_scope': 'SHACL paths only; bridge semantics explicitly requested',
    }


def compile_bridge_join(plan, schema, limit, graph_mode, graph_iri,
                        include_graph, count_per_graph, iri):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('Result limit must be 1..1000')
    if plan.get('join_type') != 'multi_key_bridge_join' or plan.get('intent') != 'list':
        raise ValueError('Unsupported bridge JOIN')
    if count_per_graph or graph_iri is not None or graph_mode not in ('default', 'all_named'):
        raise ValueError('Unsupported graph options for bridge JOIN')
    if include_graph and graph_mode != 'all_named':
        raise ValueError('Graph provenance requires all_named mode')
    if (plan.get('bridge_domain') != 'assetinventory'
            or plan.get('product_domain') != 'productcatalog'
            or plan.get('key_label') != 'AssetIdentifier'
            or plan.get('product_key_label') != 'ProductIdentifier'):
        raise ValueError('Unsupported bridge topology')
    sides = plan.get('sides')
    if (not isinstance(sides, list) or len(sides) < 3
            or len({s.get('domain') for s in sides}) != len(sides)
            or not {'assetinventory', 'productcatalog'}.issubset({s['domain'] for s in sides})):
        raise ValueError('Bridge JOIN requires distinct domains and both bridge endpoints')
    blocks = []
    for i, side in enumerate(sides):
        domain = side['domain']
        branches = side.get('branches')
        if not isinstance(branches, list) or not branches:
            raise ValueError('Bridge JOIN side lacks branches')
        key_label = 'ProductIdentifier' if domain == 'productcatalog' else 'AssetIdentifier'
        patterns = []
        for j, branch in enumerate(branches):
            predicates = branch.get('predicates')
            root, end = branch.get('root'), branch.get('end_shape')
            if not isinstance(predicates, list) or not predicates:
                raise ValueError('Bridge JOIN has empty structural path')
            structural = any(
                hops and hops[-1].get('to_shape') == end
                and [h['property'] for h in hops] == predicates
                and [e for h in hops for e in h['evidence_ids']] == branch.get('evidence_ids')
                and validate_hops(hops, schema, root)
                for hops in schema.shacl_paths(root, max_depth=len(predicates), domain=domain)
            )
            def verified_terminal(predicate, evidence, label):
                concept = schema.by_uri.get(predicate, {})
                return (concept.get('domain') == domain
                        and label in concept.get('labels', [])
                        and any(len(hops) == 1 and hops[0].get('to_shape') is None
                                and hops[0]['property'] == predicate
                                and hops[0]['evidence_ids'] == evidence
                                and validate_hops(hops, schema, end)
                                for hops in schema.shacl_paths(end, max_depth=1, domain=domain)))
            if not structural or not verified_terminal(
                    branch.get('key_predicate'), branch.get('key_evidence_ids'), key_label):
                raise ValueError('Bridge JOIN lacks verified SHACL key evidence')
            if domain == 'assetinventory':
                if not verified_terminal(branch.get('bridge_predicate'),
                                         branch.get('bridge_evidence_ids'), 'ProductIdentifier'):
                    raise ValueError('AssetInventory bridge lacks verified ProductIdentifier')
            elif 'bridge_predicate' in branch or 'bridge_evidence_ids' in branch:
                raise ValueError('Unexpected bridge property outside AssetInventory')
            variables = ([f'?root{i}_{j}']
                         + [f'?n{i}_{j}_{k}' for k in range(1, len(predicates))]
                         + [f'?entity{i}'])
            triples = [f'{variables[k]} {iri(pred)} {variables[k+1]} .'
                       for k, pred in enumerate(predicates)]
            join_var = '?productId' if domain == 'productcatalog' else '?assetId'
            triples.append(f'?entity{i} {iri(branch["key_predicate"])} {join_var} .')
            if domain == 'assetinventory':
                triples.append(f'?entity{i} {iri(branch["bridge_predicate"])} ?productId .')
            patterns.append('{\n' + '\n'.join('    ' + t for t in triples) + '\n  }')
        inner = '\n  UNION\n  '.join(patterns)
        blocks.append(f'  GRAPH ?graph{i} {{\n  {inner}\n  }}'
                      if graph_mode == 'all_named' else '  ' + inner)
    entities = [f'?entity{i}' for i in range(len(sides))]
    graphs = [f'?graph{i}' for i in range(len(sides))] if include_graph else []
    projection = ' '.join(entities + ['?assetId', '?productId'] + graphs)
    order = ' '.join(['?assetId', '?productId'] + entities)
    return ('SELECT DISTINCT ' + projection + '\nWHERE {\n'
            + '\n'.join(blocks) + '\n}\nORDER BY ' + order + f'\nLIMIT {limit}')


def compile_schema_bridge_join(plan, schema, limit, graph_mode, graph_iri,
                               include_graph, count_per_graph, iri):
    """Compile generic two-key bridge; revalidate every structural and terminal hop."""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('Result limit must be 1..1000')
    if plan.get('join_type') != 'schema_bridge_join' or plan.get('intent') != 'list':
        raise ValueError('Unsupported schema bridge JOIN')
    if count_per_graph or graph_iri is not None or graph_mode not in ('default', 'all_named'):
        raise ValueError('Unsupported graph options for schema bridge JOIN')
    if include_graph and graph_mode != 'all_named':
        raise ValueError('Graph provenance requires all_named mode')
    keys, sides = plan.get('join_keys'), plan.get('sides')
    if (not isinstance(keys, list) or len(keys) != 2 or len(set(keys)) != 2
            or not all(isinstance(k, str) and k for k in keys)
            or not isinstance(sides, list) or len(sides) < 3
            or len({s.get('domain') for s in sides}) != len(sides)
            or plan.get('bridge_domain') not in {s['domain'] for s in sides}):
        raise ValueError('Invalid generic bridge topology')
    blocks = []
    covered = set()
    for i, side in enumerate(sides):
        domain, branches = side['domain'], side.get('branches')
        if not isinstance(branches, list) or not branches:
            raise ValueError('Missing schema bridge branches')
        patterns = []
        branch_labels = set()
        for j, branch in enumerate(branches):
            predicates, root, end = (branch.get('predicates'), branch.get('root'),
                                     branch.get('end_shape'))
            if not isinstance(predicates, list) or not predicates:
                raise ValueError('Empty bridge structural path')
            valid = any(hops and hops[-1].get('to_shape') == end
                        and [h['property'] for h in hops] == predicates
                        and [e for h in hops for e in h['evidence_ids']] == branch.get('evidence_ids')
                        and validate_hops(hops, schema, root)
                        for hops in schema.shacl_paths(root, max_depth=len(predicates), domain=domain))
            def verified(predicate, evidence, label):
                concept = schema.by_uri.get(predicate, {})
                return (label in keys and concept.get('domain') == domain
                        and label in concept.get('labels', [])
                        and any(len(hops) == 1 and hops[0].get('to_shape') is None
                                and hops[0]['property'] == predicate
                                and hops[0]['evidence_ids'] == evidence
                                and validate_hops(hops, schema, end)
                                for hops in schema.shacl_paths(end, max_depth=1, domain=domain)))
            key = branch.get('key_label')
            if not valid or not verified(branch.get('key_predicate'),
                                         branch.get('key_evidence_ids'), key):
                raise ValueError('Unverified generic bridge key')
            branch_labels.add(key)
            second = branch.get('bridge_key_label')
            if domain == plan['bridge_domain']:
                if (second not in keys or second == key
                        or not verified(branch.get('bridge_predicate'),
                                        branch.get('bridge_evidence_ids'), second)):
                    raise ValueError('Unverified second key on bridge entity')
            elif second is not None or 'bridge_predicate' in branch or 'bridge_evidence_ids' in branch:
                raise ValueError('Second key outside bridge domain')
            variables = ([f'?root{i}_{j}']
                         + [f'?n{i}_{j}_{k}' for k in range(1, len(predicates))]
                         + [f'?entity{i}'])
            triples = [f'{variables[k]} {iri(pred)} {variables[k+1]} .'
                       for k, pred in enumerate(predicates)]
            triples.append(f'?entity{i} {iri(branch["key_predicate"])} ?joinKey{keys.index(key)} .')
            if second:
                triples.append(f'?entity{i} {iri(branch["bridge_predicate"])} ?joinKey{keys.index(second)} .')
            patterns.append('{\n' + '\n'.join('    ' + t for t in triples) + '\n  }')
        if domain != plan['bridge_domain']:
            if len(branch_labels) != 1:
                raise ValueError('Ambiguous non-bridge key in compiled plan')
            covered.update(branch_labels)
        inner = '\n  UNION\n  '.join(patterns)
        blocks.append(f'  GRAPH ?graph{i} {{\n  {inner}\n  }}'
                      if graph_mode == 'all_named' else '  ' + inner)
    if covered != set(keys):
        raise ValueError('Both keys require external domain coverage')
    entities = [f'?entity{i}' for i in range(len(sides))]
    graphs = [f'?graph{i}' for i in range(len(sides))] if include_graph else []
    projection = ' '.join(entities + ['?joinKey0', '?joinKey1'] + graphs)
    order = ' '.join(['?joinKey0', '?joinKey1'] + entities)
    return ('SELECT DISTINCT ' + projection + '\nWHERE {\n'
            + '\n'.join(blocks) + '\n}\nORDER BY ' + order + f'\nLIMIT {limit}')
