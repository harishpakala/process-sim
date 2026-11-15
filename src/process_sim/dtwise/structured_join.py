"""LLM intent proposal, followed by strict SHACL-only identifier join validation.

No ontology-specific domain, class, predicate, or identifier is embedded here.
"""
import json
import re
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from dtwise.query_planner import validate_hops
from dtwise.cross_domain_join import _mentioned
from dtwise.cross_domain_projection import _same


def _ask(question, catalog, domains, host, model, timeout):
    entries = []
    for c in catalog:
        if c['domain'] not in domains:
            continue
        entries.append({'id': c['id'], 'domain': c['domain'],
                        'entity_labels': c['target_labels'],
                        'properties': [{'id': p['id'], 'labels': p['labels']}
                                       for p in c['terminal']]})
    schema = {'type': 'object', 'properties': {
        'operation': {'type': 'string', 'enum': ['identifier_equality', 'unsupported']},
        'join_key': {'type': ['string', 'null']},
        'output_domain': {'type': ['string', 'null']},
        'output_property': {'type': ['string', 'null']},
        'entity_constraints': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'domain': {'type': 'string'}, 'entity': {'type': 'string'}},
            'required': ['domain', 'entity'], 'additionalProperties': False}},
        'filters': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'domain': {'type': 'string'}, 'property': {'type': 'string'},
            'operator': {'type': 'string', 'enum': ['eq']}, 'value': {'type': 'string'}},
            'required': ['domain', 'property', 'operator', 'value'],
            'additionalProperties': False}},
        'explicit_equality_authorized': {'type': 'boolean'}},
        'required': ['operation', 'join_key', 'output_domain', 'output_property',
                     'entity_constraints', 'filters', 'explicit_equality_authorized'],
        'additionalProperties': False}
    payload = {'model': model, 'stream': False, 'format': schema,
               'options': {'temperature': 0},
               'messages': [
                   {'role': 'system', 'content': (
                       'Extract only the user-requested cross-domain operation. '
                       'Return identifier_equality only when the user explicitly requests '
                       'joining/matching/associating entities across domains on a named '
                       'identifier property. "using <named identifier property>" explicitly authorizes '
                       'identifier equality when it connects two named domains. '
                       'Do not infer joins from merely mentioning two domains. '
                       'Use only exact domain, entity and property labels in the supplied '
                       'catalog. Output property is not the join key. '
                       'entity_constraints MUST contain only entity labels explicitly '
                       'mentioned in the question; otherwise return an empty array. '
                       'Never infer an entity from the output property or its owner. '
                       'Extract EVERY explicit property/value constraint into filters, '
                       'with exact literal values and eq operator. Never omit a constraint. '
                       'Filters represent property-to-literal equality only; never encode '
                       'a cross-domain join as a filter with a domain:entity value. '
                       'Do not confuse entity constraints with property/value filters. '
                       'If a constraint cannot be represented, return unsupported. '
                       'If unclear, return unsupported and null properties. '
                       'Do not infer identifier prefixes or RDF relationships.')},
                   {'role': 'user', 'content': json.dumps({'question': question, 'catalog': entries})}]}
    req = Request(host.rstrip('/') + '/api/chat',
                  data=json.dumps(payload).encode('utf-8'),
                  headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(req, timeout=timeout) as response:
            reply = json.load(response)
        return json.loads(reply['message']['content'])
    except (HTTPError, URLError, TimeoutError, OSError, KeyError, TypeError,
            json.JSONDecodeError) as exc:
        raise ValueError('Structured join interpretation failed: ' + str(exc)) from exc


def plan_structured_join(question, catalog, schema, *, host, model, timeout,
                         interpret_join=None):
    domains = sorted({str(c['domain']) for c in schema.concepts
                      if c.get('domain') and _mentioned(c['domain'], question)})
    if len(domains) != 2:
        return None  # Existing N-domain and single-domain planners remain intact.
    available = {c['domain'] for c in catalog}
    if not set(domains) <= available:
        raise ValueError('Named join domain lacks SHACL candidates')
    intent = (interpret_join(question, catalog) if interpret_join is not None
              else _ask(question, catalog, domains, host, model, timeout))
    if not isinstance(intent, dict) or intent.get('operation') != 'identifier_equality':
        raise ValueError('Cross-domain equality was not explicitly authorized')
    if intent.get('explicit_equality_authorized') is not True:
        raise ValueError('Cross-domain equality was not explicitly authorized')
    key = intent.get('join_key')
    out_domain = intent.get('output_domain')
    output = intent.get('output_property')
    if not all(isinstance(v, str) and v.strip() for v in (key, out_domain, output)):
        raise ValueError('Incomplete structured cross-domain intent')
    if not _mentioned(key, question):
        raise ValueError('Join key not explicitly named in the question')
    if out_domain not in domains:
        raise ValueError('Output domain not explicitly requested')
    if not _mentioned(output, question):
        raise ValueError('Output property not explicitly named in the question')
    constraints = intent.get('entity_constraints')
    if not isinstance(constraints, list):
        raise ValueError('Invalid entity constraints')
    constrained = {}
    for entry in constraints:
        if not isinstance(entry, dict) or entry.get('domain') not in domains:
            raise ValueError('Invalid entity constraint domain')
        label = entry.get('entity')
        if not isinstance(label, str):
            raise ValueError('Invalid entity constraint label')
        # Role exclusivity: a label explicitly selected as the join key is
        # not an entity constraint. Its SHACL validation on both sides is
        # mandatory below, so this does not authorize an unsupported key.
        if _same(label, key):
            continue
        if not _mentioned(label, question):
            # Model-suggested, unrequested entity restrictions are not authorized.
            # Discard them; SHACL path selection below must still be unique.
            continue
        # A property label is not an entity constraint. Qwen may place a
        # requested filter property in both fields. Discard that duplicate
        # classification only when the same domain/property is explicitly
        # represented in the filters; filter validation below remains strict.
        domain_candidates = [c for c in catalog if c['domain'] == entry['domain']
                             and validate_hops(c['_hops'], schema, c['root'])]
        matching_entities = [c for c in domain_candidates
                             if any(_same(entity_label, label) or entity_label.casefold() == label.casefold()
                                    for entity_label in c['target_labels'])]
        if not matching_entities:
            matching_filter = any(
                isinstance(f, dict) and f.get('domain') == entry['domain']
                and isinstance(f.get('property'), str)
                and _same(f['property'], label)
                for f in (intent.get('filters') or []))
            if matching_filter:
                continue
            raise ValueError('Entity constraint not supported by SHACL: ' + label)
        if entry['domain'] in constrained:
            # Resolve alternative labels against SHACL-backed catalog candidates.
            # Two names are equivalent only when their validated candidate sets
            # identify exactly the same single candidate. Do not guess aliases.
            def matching_candidates(entity_label):
                return {c['id'] for c in catalog
                        if c['domain'] == entry['domain']
                        and any(_same(candidate_label, entity_label)
                                or candidate_label.casefold() == entity_label.casefold()
                                for candidate_label in c['target_labels'])
                        and validate_hops(c['_hops'], schema, c['root'])}
            first = matching_candidates(constrained[entry['domain']])
            second = matching_candidates(label)
            if not (len(first) == 1 and first == second):
                raise ValueError('Conflicting entity constraints for ' + entry['domain'])
            continue
        constrained[entry['domain']] = label
    # Filters are model-proposed, but neither property nor value may be invented.
    filters = intent.get('filters')
    if not isinstance(filters, list):
        raise ValueError('Structured join must explicitly account for property filters')
    validated_requests = []
    for f in filters:
        if not isinstance(f, dict) or f.get('domain') not in domains or f.get('operator') != 'eq':
            raise ValueError('Unsupported structured join filter')
        prop, value = f.get('property'), f.get('value')
        # A model can redundantly express a property-to-property equality join
        # as a property-to-entity-reference filter. Such a reference is NOT a
        # literal constraint. Suppress it only if it points to the explicitly
        # requested entity in the *other* domain and the property is the join
        # key. The subsequent unique SHACL path checks still validate the key
        # on both sides. Any other unrequested filter remains an error.
        if isinstance(prop, str) and isinstance(value, str) and ':' in value \
                and value not in question and _same(prop, key):
            ref_domain, ref_entity = value.split(':', 1)
            opposite = [d for d in domains if d != f['domain']]
            if len(opposite) == 1 and ref_domain == opposite[0] and any(
                isinstance(e, dict) and e.get('domain') == ref_domain
                and isinstance(e.get('entity'), str)
                and _same(e['entity'], ref_entity)
                and _mentioned(e['entity'], question)
                for e in constraints
            ):
                continue
        if not isinstance(prop, str) or not _mentioned(prop, question):
            raise ValueError('Filter property not explicitly requested')
        if not isinstance(value, str) or not value or value not in question:
            raise ValueError('Filter value not explicitly present in question')
        if len(value) > 200 or any(ord(ch) < 32 for ch in value):
            raise ValueError('Invalid filter value')
        validated_requests.append(f)
    # Detect omitted literal-like identifiers (e.g. equipment codes) without
    # knowing their vocabulary. The model cannot silently drop these values.
    literal_tokens = set(re.findall(r'(?<![\w/])(?=[A-Za-z0-9_-]*\d)[A-Za-z][A-Za-z0-9_]*-[A-Za-z0-9_-]+\b', question))
    for token in literal_tokens:
        if not any(token in f['value'] for f in validated_requests):
            raise ValueError('Unrepresented identifier-like literal in structured join: ' + token)
    sides = {}
    for domain in domains:
        choices = {}
        for c in catalog:
            if c['domain'] != domain:
                continue
            if domain in constrained and not any(_same(label, constrained[domain])
                                                 for label in c['target_labels']):
                continue
            if not validate_hops(c['_hops'], schema, c['root']):
                continue
            keys = [p for p in c['terminal']
                    if any(_same(label, key) for label in p['labels'])
                    and validate_hops([p['_hop']], schema, c['end'])]
            outs = ([p for p in c['terminal']
                     if any(_same(label, output) for label in p['labels'])
                     and validate_hops([p['_hop']], schema, c['end'])]
                    if domain == out_domain else [None])
            for kp in keys:
                for op in outs:
                    signature = (c['root'], tuple(c['predicates']), c['end'],
                                 kp['predicate'], op['predicate'] if op else None)
                    choices[signature] = (c, kp, op)
        if len(choices) != 1:
            raise ValueError(f'Expected one SHACL-validated {domain} join/output path; found {len(choices)}')
        sides[domain] = next(iter(choices.values()))
    validated_filters = []
    for f in validated_requests:
        c = sides[f['domain']][0]
        matches = {}
        for p in c['terminal']:
            if any(_same(label, f['property']) for label in p['labels'] + [p['predicate'].rsplit('/', 1)[-1]]) \
                    and validate_hops([p['_hop']], schema, c['end']):
                matches[p['predicate']] = p
        if len(matches) != 1:
            raise ValueError('Expected one SHACL-validated filter property for ' + f['domain'])
        p = next(iter(matches.values()))
        validated_filters.append({'domain': f['domain'], 'predicate': p['predicate'],
                                  'evidence_ids': list(p['_hop']['evidence_ids']),
                                  'operator': 'eq', 'value': f['value']})
    source_domain = next(d for d in domains if d != out_domain)
    def branch(c, kp):
        return {'domain': c['domain'], 'root': c['root'], 'end_shape': c['end'],
                'predicates': list(c['predicates']),
                'evidence_ids': [e for h in c['_hops'] for e in h['evidence_ids']],
                'key_predicate': kp['predicate'],
                'key_evidence_ids': list(kp['_hop']['evidence_ids'])}
    sc, sk, _ = sides[source_domain]
    tc, tk, op = sides[out_domain]
    return {'query_type': 'SELECT', 'intent': 'list',
            'join_type': 'cross_domain_projection',
            'planner': 'structured_shacl_identifier_projection',
            'join_key_label': key,
            'source': branch(sc, sk), 'target': branch(tc, tk),
            'filter': None, 'filters': validated_filters,
            'projection': {'predicate': op['predicate'],
                           'evidence_ids': list(op['_hop']['evidence_ids'])},
            'validation_scope': 'Explicit caller equality intent; all paths and predicates verified from SHACL'}
