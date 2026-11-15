"""Deterministic repair of unambiguous SHACL edge endpoints; no inferred joins."""
from copy import deepcopy
from .unified_ir import validate_ir

NODE = 'http://www.w3.org/ns/shacl#node'


def resolve_shapes(plan, index, mappings=None):
    """Return validated plan with unique SHACL edge shapes repaired, or reject.

    Does not change predicates, aliases, domains, filters, or projections.
    Multiple incompatible candidates always reject.
    """
    out = deepcopy(plan)
    entities = {n['alias']: n for n in out.get('entities', [])}
    if len(entities) != len(out.get('entities', [])):
        raise ValueError('Duplicate entity aliases')
    proposals = {}
    for edge in out.get('edges', []):
        if edge.get('kind') != 'shacl':
            continue
        source = entities.get(edge.get('from'))
        target = entities.get(edge.get('to'))
        if source is None or target is None:
            raise ValueError('Unknown SHACL edge endpoint')
        if source['domain'] != target['domain']:
            raise ValueError('Cross-domain SHACL edge forbidden without mapping evidence')
        domain, predicate = source['domain'], edge.get('predicate')
        candidates = set()
        for path in index['shape_paths']:
            if path.get('domain') != domain or path.get('path') != predicate or not path.get('evidence'):
                continue
            for rel in index['relationships']:
                if (rel.get('domain') == domain and rel.get('predicate') == NODE
                    and rel.get('subject') == path['property_shape']):
                    candidates.add((path['node_shape'], rel['object']))
        if not candidates:
            raise ValueError('No verified SHACL edge for ' + str(predicate))
        # Preserve either matching endpoint as a constraint, where possible.
        matched = {c for c in candidates if c[0] == source['shape'] and c[1] == target['shape']}
        if not matched:
            matched = {c for c in candidates if c[1] == target['shape']}
        if not matched:
            matched = {c for c in candidates if c[0] == source['shape']}
        if len(matched) != 1:
            raise ValueError('Ambiguous SHACL edge shapes for ' + str(predicate))
        left_shape, right_shape = next(iter(matched))
        for alias, shape in ((edge['from'], left_shape), (edge['to'], right_shape)):
            if alias in proposals and proposals[alias] != shape:
                raise ValueError('Conflicting SHACL shape constraints for ' + alias)
            proposals[alias] = shape
    for alias, shape in proposals.items():
        original = entities[alias]['shape']
        if original == shape:
            continue
        # Never repair a shape if that changes the meaning of an explicitly
        # requested property/filter or an independently verified mapping edge.
        predicates = [p['predicate'] for p in out.get('projections', []) if p.get('entity') == alias]
        def walk_filter(f):
            if not isinstance(f, dict): return
            if f.get('entity') == alias and 'predicate' in f:
                predicates.append(f['predicate'])
            for child in f.get('children', []): walk_filter(child)
            walk_filter(f.get('child'))
        walk_filter(out.get('filters'))
        if any(e.get('kind') == 'mapping' and alias in (e.get('from'), e.get('to'))
               for e in out.get('edges', [])):
            raise ValueError('Cannot repair entity involved in mapping join: ' + alias)
        for predicate in predicates:
            if not any(p['domain'] == entities[alias]['domain'] and
                       p['node_shape'] == shape and p['path'] == predicate and p.get('evidence')
                       for p in index['shape_paths']):
                raise ValueError('Shape repair conflicts with requested property: ' + predicate)
        entities[alias]['shape'] = shape
    validate_ir(out, index, mappings=mappings)
    return out
