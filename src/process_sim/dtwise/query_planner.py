"""Ontology-grounded planner: root-to-target traversal plus optional existence condition.

Semantic matching is lexical (not LLM-based); every chosen predicate is validated
against complete SHACL structural evidence before compilation.
"""
import re

SH = 'http://www.w3.org/ns/shacl#'
STOP = {'list','show','find','get','retrieve','give','me','all','the','a','an','in','of','from','for','associated','with','are','which','what','is','there','many','how','number','total','count','and','their','its','have','has','that','do','does'}
COUNT = {'count','many','number','total'}
LIST = {'list','show','find','get','retrieve','which','what'}
UNSUPPORTED = {'where','when','between','before','after','greater','less','compare','connected','without','only','whose','not','except','or'}


def tokens(text):
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(text))
    words = set(re.findall(r'[a-z0-9]+', text.lower()))
    return words | {w[:-3]+'y' if w.endswith('ies') and len(w)>4 else w[:-1] if w.endswith('s') and not w.endswith('ss') and len(w)>3 else w for w in words}


def local(uri):
    return str(uri).rstrip('/#').rsplit('/', 1)[-1].rsplit('#', 1)[-1]


def validate_hops(hops, schema, start_shape=None):
    if not hops or (start_shape is not None and hops[0]['from_shape'] != start_shape):
        return False
    index = schema.relationship_by_id
    for i, hop in enumerate(hops):
        ids = hop.get('evidence_ids') or []
        destination = hop.get('to_shape')
        if len(ids) != (3 if destination else 2) or len(ids) != len(set(ids)):
            return False
        expected = {(hop['from_shape'], SH+'property', hop['property_shape']),
                    (hop['property_shape'], SH+'path', hop['property'])}
        if destination:
            expected.add((hop['property_shape'], SH+'node', destination))
        actual = set()
        for id_ in ids:
            edge = index.get(id_)
            if edge is None:
                return False
            actual.add((edge.get('subject'), edge.get('predicate'), edge.get('object')))
        if actual != expected:
            return False
        if i and hops[i-1].get('to_shape') != hop['from_shape']:
            return False
        if i < len(hops)-1 and not destination:
            return False
    return True


def grounded(path, schema):
    hops = path.get('hops') or []
    return bool(path.get('path_valid') and path.get('path_complete') and
                path.get('path_type') == 'node_traversal' and
                path.get('properties') == [h['property'] for h in hops] and
                hops and hops[-1]['to_shape'] == path.get('end_shape') and
                validate_hops(hops, schema, path.get('start_shape')) and
                set(path.get('evidence_ids') or []) == {e for h in hops for e in h['evidence_ids']})


def _shape_words(schema, uri):
    return tokens(' '.join(schema.by_uri.get(uri, {}).get('labels') or []))


def _root_candidates(schema, q):
    # Domain roots are schema shapes with a label matching a named domain.
    domains = {c.get('domain') for c in schema.concepts if c.get('domain')}
    mentioned = domains & q
    if len(mentioned) != 1:
        raise ValueError('Question must specify exactly one known schema domain')
    domain = next(iter(mentioned))
    roots = [c['uri'] for c in schema.concepts if c.get('domain') == domain and
             c.get('kind') == 'shape' and domain in _shape_words(schema, c['uri'])]
    # Some indexes label the root as a class, with a distinct shape record.
    if not roots:
        roots = [c['uri'] for c in schema.concepts if c.get('domain') == domain and
                 domain in _shape_words(schema, c['uri']) and schema.outgoing.get(c['uri'])]
    return domain, sorted(set(roots))


def _value_filter(question):
    """Recognize only explicit quoted lexical equality; never infer a datatype."""
    # Values must be quoted to avoid treating ontology labels as literal values.
    quote = r'["\']([^"\']{1,200})["\']'
    match = re.search(r'\b(?:equal\s+to|equals|is)\s+' + quote, question, re.I)
    if match:
        return {'operator': 'lexical_equals', 'value': match.group(1)}
    if re.search(r'\b(?:equal\s+to|equals|is)\s+["\']', question, re.I):
        raise ValueError('Invalid quoted comparison value')
    return None


def plan_question(question, paths, schema):
    value_filter = _value_filter(question)
    q = tokens(question)
    if q & UNSUPPORTED:
        raise ValueError('Unsupported comparison, negation, disjunction or complex filter')
    intent = 'count' if q & COUNT else 'list' if q & LIST else None
    if not intent:
        raise ValueError('Only list and count questions are supported')
    domain, roots = _root_candidates(schema, q)
    meaningful = q - STOP - {domain} - ({'equal','equals','to'} if value_filter else set())
    if value_filter:
        meaningful -= tokens(value_filter['value'])
    # Use the full SHACL graph to recover root paths, not only retrieval-ranked paths.
    # Retrieval is still used upstream for evidence discovery and diagnostics.
    candidates = []
    for root in roots:
        for hops in schema.shacl_paths(root, max_depth=6, domain=domain):
            if not hops[-1].get('to_shape') or not validate_hops(hops, schema, root):
                continue
            end = hops[-1]['to_shape']
            words = _shape_words(schema, end)
            match = meaningful & words
            if not match:
                continue
            last = tokens(local(hops[-1]['property']))
            if not (meaningful & last):
                continue
            raw_question = set(re.findall(r'[a-z0-9]+', question.lower())) - STOP
            raw_end = {x.lower() for label in schema.by_uri.get(end, {}).get('labels', []) for x in re.findall(r'[A-Za-z0-9]+', label)}
            exact = len(raw_end & raw_question)
            penalty = 22 if local(hops[-1]['property']).lower().endswith('s') else 0
            score = exact*10 + len(match)*4 + len(meaningful & last)*2 - penalty + len(hops)*.2
            candidates.append((score, root, hops))
    if not candidates:
        raise ValueError('No domain-rooted SHACL path matches the requested entity')
    candidates.sort(key=lambda x: (-x[0], -len(x[2]), x[1], tuple(h['property'] for h in x[2])))
    score, root, hops = candidates[0]
    if len(candidates)>1 and candidates[1][0] == score and [h['property'] for h in candidates[1][2]] != [h['property'] for h in hops]:
        raise ValueError('Ambiguous target path')
    end = hops[-1]['to_shape']
    # 'have/has' introduces a positive existence condition. Select an outgoing
    # SHACL terminal property whose label is explicitly present in the question.
    existence = bool(re.search(r'\b(have|has|having)\b', question.lower()))
    if value_filter and not existence:
        raise ValueError('Value comparison requires a named property introduced by have/has')
    condition = None
    if existence:
        matches = []
        for extension in schema.shacl_paths(end, max_depth=1, domain=domain):
            hop = extension[0]
            if hop['to_shape'] is not None or not validate_hops([hop], schema, end):
                continue
            prop = schema.by_uri.get(hop['property'], {})
            prop_words = tokens(' '.join(prop.get('labels') or []) + ' ' + local(hop['property'])) - {'has'}
            matched = meaningful & prop_words
            # Require full multiword property label match to prevent choosing a
            # coincidental 'variable' property from an unrelated relationship.
            name_words = tokens(local(hop['property'])) - {'has'}
            if matched and name_words <= meaningful:
                matches.append((len(name_words), hop))
        if not matches:
            raise ValueError('No SHACL-verified terminal property matches the requested existence condition')
        matches.sort(key=lambda x: -x[0])
        if len(matches)>1 and matches[0][0] == matches[1][0] and matches[0][1]['property'] != matches[1][1]['property']:
            raise ValueError('Ambiguous existence condition')
        condition = matches[0][1]
    evidence = [e for h in hops for e in h['evidence_ids']]
    plan = {'query_type':'SELECT','intent':intent,'domain':domain,
            'target_variable':'entity','predicates':[h['property'] for h in hops],
            'start_shape':root,'end_shape':end,'evidence_ids':evidence,
            'path_score':round(score,3), 'validation_scope':'Verified SHACL structural triples; instance data not verified'}
    if condition:
        plan['condition'] = {'type':'lexical_equals' if value_filter else 'exists_property','predicate':condition['property'],
                             'from_shape':end,'evidence_ids':condition['evidence_ids']}
        if value_filter:
            plan['condition']['value'] = value_filter['value']
    return plan
