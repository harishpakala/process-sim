"""Opt-in DTwise unified IR end-to-end CLI; never modifies existing main.py."""
import os
import argparse
import base64
import binascii
import json
import re
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .graph_compiler import compile_graph_ir
from .unified_ir import validate_ir
from .shape_resolver import resolve_shapes


def _shape_display_metadata(shape):
    """Decode only canonical Base64 URI path segments; never alter the shape IRI."""
    segment = shape.rstrip('/').rsplit('/', 1)[-1]
    if not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}', segment):
        return {}
    try:
        encoded = segment.replace('-', '+').replace('_', '/')
        decoded = base64.b64decode(encoded + '=' * (-len(encoded) % 4),
                                   validate=True).decode('utf-8')
    except (ValueError, UnicodeError, binascii.Error):
        return {}
    if not decoded or any(ord(c) < 32 or ord(c) == 127 for c in decoded):
        return {}
    if not decoded.endswith('/nodeShape'):
        return {}
    source_path = decoded[:-len('/nodeShape')]
    if not source_path or not re.fullmatch(r'[A-Za-z0-9_.-]+', source_path):
        return {}
    return {'source_path': source_path,
            'display_name': source_path.rsplit('.', 1)[-1]}


def catalog_from_schema(index):
    shapes = {}
    for x in index['shape_paths']:
        if not x.get('evidence'): continue
        key = (x['domain'], x['node_shape'])
        shapes.setdefault(key, set()).add(x['path'])
    rel = {(x['subject'], x['object']) for x in index['relationships']
           if x['predicate'] == 'http://www.w3.org/ns/shacl#node'}
    edges = []
    for p in index['shape_paths']:
        if not p.get('evidence'): continue
        for target_domain, target_shape in shapes:
            if target_domain == p['domain'] and (p['property_shape'], target_shape) in rel:
                edges.append({'domain':p['domain'], 'from_shape':p['node_shape'],
                              'predicate':p['path'], 'to_shape':target_shape})
    return {'entities':[{'domain':d,'shape':s,'properties':sorted(props),
                         **_shape_display_metadata(s)}
                        for (d,s),props in sorted(shapes.items())],
            'shacl_edges':edges}


def _compact_catalog_symbols(catalog):
    """Lossless SHACL IRI symbols; no entity/property selection is performed."""
    symbols = {}
    for entity in catalog['entities']:
        symbols.setdefault(entity['shape'], 'S' + str(sum(k.startswith('S') for k in symbols.values())))
        for predicate in entity['properties']:
            symbols.setdefault(predicate, 'P' + str(sum(k.startswith('P') for k in symbols.values())))
    for edge in catalog['shacl_edges']:
        for key in ('from_shape', 'to_shape', 'predicate'):
            iri = edge[key]
            prefix = 'P' if key == 'predicate' else 'S'
            symbols.setdefault(iri, prefix + str(sum(k.startswith(prefix) for k in symbols.values())))
    reverse = {symbol: iri for iri, symbol in symbols.items()}
    def encode(value):
        if isinstance(value, dict):
            return {k: encode(v) for k, v in value.items()}
        if isinstance(value, list):
            return [encode(v) for v in value]
        return symbols.get(value, value) if isinstance(value, str) else value
    return encode(catalog), symbols, reverse


def _resolve_catalog_symbols(plan, reverse):
    """Resolve only IRI-bearing IR fields; never change filter literal values."""
    def resolve(value, key=None):
        if isinstance(value, dict):
            return {k: resolve(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve(v, key) for v in value]
        if isinstance(value, str) and key in ('shape', 'predicate', 'left_predicate',
                                               'right_predicate'):
            if value in reverse:
                return reverse[value]
            if re.fullmatch(r'[SP]\\d+', value):
                raise ValueError('Unknown catalog symbol: ' + value)
        return value
    return resolve(plan)


def _request_json(url, payload, timeout):
    req = Request(url, data=json.dumps(payload).encode('utf-8'),
                  headers={'Content-Type':'application/json'}, method='POST')
    with urlopen(req, timeout=timeout) as response:
        return json.load(response)


def normalize_single_filter(plan):
    """Normalize only an unambiguous one-item filter list; never rewrite literals."""
    filters = plan.get('filters')
    if isinstance(filters, list):
        if len(filters) != 1 or not isinstance(filters[0], dict):
            raise ValueError('filters list must contain exactly one filter object; use and/or for multiple filters')
        plan = dict(plan)
        plan['filters'] = filters[0]
    return plan


def validate_planner_output(plan):
    """Reject catalog fragments and malformed plans before semantic validation."""
    if not isinstance(plan, dict):
        raise ValueError('Planner output must be a JSON object')
    if 'unsupported' in plan:
        reason = plan['unsupported']
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('Malformed unsupported response')
        raise ValueError('Planner rejected query: ' + reason)
    required = ('ir_version', 'entities', 'edges', 'projections', 'filters',
                'operation', 'return_entities')
    missing = [k for k in required if k not in plan]
    if missing:
        raise ValueError('Planner returned a schema fragment or incomplete IR; missing: '
                         + ', '.join(missing) + '; received: '
                         + json.dumps(plan, ensure_ascii=False)[:1500])
    if plan['ir_version'] != '1.0':
        raise ValueError('Unsupported planner IR version')
    if not isinstance(plan['entities'], list) or not plan['entities']:
        raise ValueError('IR entities must be a nonempty list')
    if not isinstance(plan['edges'], list) or not isinstance(plan['projections'], list):
        raise ValueError('IR edges and projections must be lists')
    if not isinstance(plan['operation'], dict) or plan['operation'].get('type') not in ('select', 'count'):
        raise ValueError('IR operation must be select or count')
    if not isinstance(plan['return_entities'], bool):
        raise ValueError('IR return_entities must be boolean')
    for entity in plan['entities']:
        if not isinstance(entity, dict) or not all(isinstance(entity.get(k), str) and entity[k]
                                                    for k in ('alias', 'domain', 'shape')):
            raise ValueError('Malformed IR entity')
    for edge in plan['edges']:
        if not isinstance(edge, dict) or edge.get('kind') not in ('shacl', 'mapping'):
            raise ValueError('Malformed IR edge')
    for projection in plan['projections']:
        if not isinstance(projection, dict) or not all(isinstance(projection.get(k), str) and projection[k]
                                                       for k in ('entity', 'predicate', 'as')):
            raise ValueError('Malformed IR projection')
    if not plan['projections'] and plan['operation']['type'] == 'select' and not plan['return_entities']:
        raise ValueError('Select plan must project a property or return entities')
    ordering = plan.get('order_by', [])
    if not isinstance(ordering, list):
        raise ValueError('order_by must be a list')
    if plan.get('result_limit') is not None and type(plan['result_limit']) is not int:
        raise ValueError('result_limit must be an integer')
    return plan


def _focused_catalog(catalog, question):
    """Prioritize explicitly named domains, but keep other domains for inferred joins."""
    domains = {x['domain'] for x in catalog['entities']}
    mentioned = {d for d in domains if re.search(r'(?<![a-z0-9])' + re.escape(d.lower())
                                                   + r'(?![a-z0-9])', question.lower())}
    if not mentioned:
        return catalog, mentioned
    selected = [x for x in catalog['entities'] if x['domain'] in mentioned]
    selected_shapes = {(x['domain'], x['shape']) for x in selected}
    selected_edges = [x for x in catalog['shacl_edges']
                      if (x['domain'], x['from_shape']) in selected_shapes]
    return {'entities': selected, 'shacl_edges': selected_edges}, mentioned



def _prompt_catalog(question, catalog):
    """Reduce only unambiguous direct-property prompts using SHACL evidence.

    All matching owning shapes are retained; ambiguity is never resolved here.
    Traversals, joins, and questions without explicit property evidence keep the
    full focused catalog. Validation always uses the original full index.
    """
    if traversal_requirement(question, catalog) or re.search(
            r'\\b(?:relationship|related|connected|link(?:ed)?|join)\\b',
            question, re.I):
        return catalog
    # Resolve exact schema-local names and their simple plural forms only.
    # Keep every candidate when a name is ambiguous; never select an owner.
    question_tokens = {token.lower() for token in
                       re.findall(r'[A-Za-z][A-Za-z0-9_]*', question)}
    requested = set(_explicit_property_requirements(question, catalog).values())
    for entity in catalog['entities']:
        for predicate in entity['properties']:
            local = re.split(r'[/#]', predicate)[-1]
            names = {local.lower()}
            if local.startswith('has') and len(local) > 3:
                names.add(local[3:].lower())
            if any(name + 's' in question_tokens or
                   (name.endswith('y') and name[:-1] + 'ies' in question_tokens)
                   for name in names):
                requested.add(predicate)
    if not requested:
        return catalog
    candidates = [entity for entity in catalog['entities']
                  if requested.intersection(entity['properties'])]
    # Do not trim if a question spans properties that require separate owners:
    # it may need a relationship the planner must discover.
    if not any(requested.issubset(set(entity['properties'])) for entity in candidates):
        return catalog
    selected = {(entity['domain'], entity['shape']) for entity in candidates}
    edges = [edge for edge in catalog['shacl_edges']
             if (edge['domain'], edge['from_shape']) in selected
             and (edge['domain'], edge['to_shape']) in selected]
    return {'entities': candidates, 'shacl_edges': edges}



def _cross_domain_prompt_catalog(question, catalog, mappings, mentioned):
    """Keep SHACL-backed named types, property owners and mapping endpoints.

    Do not resolve ambiguous owners or infer mappings. Preserve all named
    domains and fall back to the focused catalog when evidence is insufficient.
    """
    if len(mentioned) < 2:
        return _prompt_catalog(question, catalog)
    question_lower = question.lower()
    tokens = set(re.findall(r'[a-z0-9]+', question_lower))
    relevant_mappings = [
        m for m in (mappings or [])
        if m.get('verified') is True and m.get('evidence_ids')
        and m.get('left_domain') in mentioned
        and m.get('right_domain') in mentioned
    ]
    mapping_keys = {
        (m['left_domain'], m['left_property']) for m in relevant_mappings
    } | {
        (m['right_domain'], m['right_property']) for m in relevant_mappings
    }
    selected = []
    for entity in catalog['entities']:
        domain = entity['domain']
        display = entity.get('display_name', '')
        name_match = bool(display and re.search(
            r'(?<![a-z0-9])' + re.escape(display.lower()) +
            r'(?![a-z0-9])', question_lower))
        property_match = any(
            re.split(r'[/#]', p)[-1].lower().removeprefix('has') in tokens
            for p in entity['properties'])
        mapping_match = any(
            (domain, p) in mapping_keys for p in entity['properties'])
        if name_match or property_match or mapping_match:
            selected.append(entity)
    if not all(any(e['domain'] == domain for e in selected)
               for domain in mentioned):
        return catalog
    selected_keys = {(e['domain'], e['shape']) for e in selected}
    edges = [edge for edge in catalog['shacl_edges']
             if (edge['domain'], edge['from_shape']) in selected_keys
             and (edge['domain'], edge['to_shape']) in selected_keys]
    return {'entities': selected, 'shacl_edges': edges}


def property_owner_hints(question, catalog):
    """Evidence-backed candidate owners for explicitly named properties.

    Never infer property synonyms or select a shape on behalf of the planner.
    Ambiguous property names are left as multiple candidates.
    """
    requirements = _explicit_property_requirements(question, catalog)
    hints = []
    for name, predicate in sorted(requirements.items()):
        owners = [{'domain': entity['domain'], 'shape': entity['shape'],
                   'display_name': entity.get('display_name')}
                  for entity in catalog['entities']
                  if predicate in entity['properties']]
        if owners:
            hints.append({'question_term': name, 'predicate': predicate,
                          'candidate_owners': owners})
    return hints


def traversal_requirement(question, catalog):
    """Conservative structural coverage check, not a natural-language path resolver.

    A relationship expressed as a traversal must not disappear from the IR.
    The actual hop predicates and shapes are still selected by the model and
    independently checked against SHACL by compile_graph_ir.
    """
    traversal_words = re.search(
        r"\b(?:through|via|travers(?:e|al|ing)|reached|parent|child|"
        r"follow(?:ing)?|\d+[- ]hop|multi[- ]hop)\b", question, re.I)
    if not traversal_words:
        return False
    return bool(catalog.get('shacl_edges'))


def _explicit_property_requirements(question, catalog):
    """Find only unambiguous, explicitly named SHACL properties; never infer synonyms."""
    words = re.findall(r'[A-Za-z][A-Za-z0-9_]*', question)
    tokens = {word.lower() for word in words}
    properties = {}
    traversal_predicates = {edge['predicate'] for edge in catalog.get('shacl_edges', [])}
    for entity in catalog['entities']:
        for predicate in entity['properties']:
            local = re.split(r'[/#]', predicate)[-1]
            names = {local.lower()}
            # A relationship's object-class name (e.g. InstrumentationFunction)
            # is not evidence that the relationship itself was requested as an
            # output. Require its full predicate name when it is a SHACL edge.
            if local.startswith('has') and len(local) > 3 and predicate not in traversal_predicates:
                names.add(local[3:].lower())
            for name in names & tokens:
                properties.setdefault(name, set()).add(predicate)
    return {name: next(iter(iris)) for name, iris in properties.items() if len(iris) == 1}


def check_semantic_coverage(plan, question, catalog, mentioned):
    actual = {x['domain'].lower() for x in plan['entities']}
    missing = mentioned - actual
    if missing:
        raise ValueError('Explicitly mentioned domain omitted: ' + repr(sorted(missing)))
    if traversal_requirement(question, catalog) and not plan['edges']:
        candidates = [e for e in catalog['shacl_edges'] if
                      e['domain'] in actual]
        raise ValueError('Requested traversal omitted: edges=[]; '
                         'candidate verified SHACL edges: '
                         + json.dumps(candidates[:15], ensure_ascii=False))
    # Only check property names explicitly present in the question and unique
    # in the evidenced catalog. This is a conservative completeness check, not
    # a semantic resolver: it never inserts, replaces, or guesses predicates.
    requirements = _explicit_property_requirements(question, catalog)
    projected = {p['predicate'] for p in plan['projections']}
    def filter_predicates(node):
        if not isinstance(node, dict):
            return set()
        found = {node['predicate']} if isinstance(node.get('predicate'), str) else set()
        for child in node.get('args', []):
            found |= filter_predicates(child)
        if isinstance(node.get('arg'), dict):
            found |= filter_predicates(node['arg'])
        return found
    filtered = filter_predicates(plan.get('filters'))
    before_where = re.split(r'\bwhere\b', question, maxsplit=1, flags=re.I)
    # In cross-domain 'Get X for Y with Z VALUE', Y/Z are input
    # constraints, not additional requested output projections.
    output_clause = before_where[0]
    if len(mentioned) > 1:
        output_clause = re.split(r'\bfor\s+(?=[A-Za-z]+\s)', output_clause,
                                 maxsplit=1, flags=re.I)[0]
    output_names = _explicit_property_requirements(output_clause, catalog)
    for name, predicate in output_names.items():
        if plan['operation']['type'] == 'select' and predicate not in projected:
            raise ValueError('Explicit requested projection omitted: ' + predicate)
    if len(before_where) == 2:
        filter_names = _explicit_property_requirements(before_where[1], catalog)
        for name, predicate in filter_names.items():
            if predicate not in filtered:
                raise ValueError('Explicit requested filter omitted: ' + predicate)
        # Exact literals explicitly introduced by "is" must be preserved.
        for literal in re.findall(r'\bis\s+([^\s,;]+)', before_where[1], flags=re.I):
            literal = literal.rstrip('.')
            def values(node):
                if not isinstance(node, dict):
                    return []
                return ([str(node['value'])] if 'value' in node else []) + [
                    v for child in node.get('args', []) for v in values(child)] + values(node.get('arg'))
            if literal not in values(plan.get('filters')):
                raise ValueError('Explicit requested filter literal omitted: ' + literal)
    # A named property followed by an explicit value after 'with' is an
    # input filter, even without WHERE. Scope ambiguous names to the model's
    # selected, SHACL-evidenced entity shapes. This checks completeness only:
    # it never adds a filter, chooses an entity, or repairs the model's plan.
    if len(mentioned) > 1:
        for property_name, literal in re.findall(
                r'\bwith\s+([A-Za-z][A-Za-z0-9_]*)\s+([A-Za-z0-9][A-Za-z0-9_-]*)',
                question, flags=re.I):
            candidates = set()
            for selected in plan['entities']:
                for entity in catalog['entities']:
                    if (entity['domain'] != selected['domain'] or
                            entity['shape'] != selected['shape']):
                        continue
                    for iri in entity['properties']:
                        local = re.split(r'[/#]', iri)[-1].lower()
                        names = {local}
                        if local.startswith('has') and len(local) > 3:
                            names.add(local[3:])
                        if property_name.lower() in names:
                            candidates.add((selected['alias'], iri))
            if len(candidates) != 1:
                # No unambiguous selected-shape evidence: never guess.
                continue
            alias, predicate = next(iter(candidates))
            def exact_filter(node):
                if not isinstance(node, dict):
                    return False
                if (node.get('op') == 'eq' and node.get('entity') == alias
                        and node.get('predicate') == predicate
                        and node.get('value') == literal):
                    return True
                return any(exact_filter(child) for key in ('args', 'children')
                           for child in node.get(key, [])) or any(
                               exact_filter(node.get(key)) for key in ('arg', 'child'))
            if not exact_filter(plan.get('filters')):
                raise ValueError('Explicit input constraint omitted: '
                                 + property_name + ' = ' + literal)
    # Explicit substring clauses are requirements even without a WHERE keyword.
    # This is a coverage guard only: the model must still select the entity,
    # predicate, filter operator and literal; no IR is synthesized here.
    substring_clauses = re.findall(
        r'\b([A-Za-z][A-Za-z0-9_]*)\s+(?:containing|contains)\s+([^\s,;?]+)',
        question, flags=re.I)
    if substring_clauses:
        requirements_by_name = _explicit_property_requirements(question, catalog)
        def filter_leaves(node):
            if not isinstance(node, dict):
                return []
            leaves = [node] if node.get('predicate') else []
            for key in ('args', 'children'):
                for child in node.get(key, []):
                    leaves.extend(filter_leaves(child))
            for key in ('arg', 'child'):
                leaves.extend(filter_leaves(node.get(key)))
            return leaves
        leaves = filter_leaves(plan.get('filters'))
        for property_name, literal in substring_clauses:
            predicate = requirements_by_name.get(property_name.lower())
            if predicate is None:
                continue  # Ambiguous/unknown property: do not guess a predicate.
            literal = literal.rstrip('.')
            if not any(leaf.get('op') == 'contains' and
                       leaf.get('predicate') == predicate and
                       leaf.get('value') == literal for leaf in leaves):
                raise ValueError('Explicit substring filter omitted or incorrect: '
                                 + property_name + ' containing ' + literal)
    # A direct SELECT property lookup without a WHERE clause must not invent
    # a literal filter. COUNT/relationship questions may legitimately use
    # property-existence constraints without an explicit WHERE.
    if (len(before_where) == 1 and output_names and
            plan['operation']['type'] == 'select' and
            not traversal_requirement(question, catalog) and
            len(mentioned) <= 1 and
            not substring_clauses and
            plan.get('filters') is not None):
        raise ValueError('Unrequested filter in direct property lookup')
    # An unrequested traversal cannot be added to a simple property lookup.
    # Leave traversals allowed when the question actually requests a relationship.
    if len(mentioned) <= 1 and not traversal_requirement(question, catalog) and not re.search(
            r'\b(?:relationship|related|connected|link(?:ed)?|join)\b', question, re.I):
        if output_names and plan['edges']:
            raise ValueError('Unrequested SHACL traversal in direct property lookup')
    return plan

def generate_ir(question, schema, *, model='qwen2.5-coder:3b',
                ollama_host=None, timeout=120, mappings=None, diagnostics=None,
                compact_prompt=False, keep_alive=None,
                owner_hints=False, prompt_diagnostics=None, compact_catalog=False):
    index = json.loads(Path(schema).read_text(encoding='utf-8'))
    full_catalog = catalog_from_schema(index)
    catalog, mentioned = _focused_catalog(full_catalog, question)
    # Reduce the model-facing catalog only with positive SHACL/mapping evidence.
    # The full indexed catalog remains authoritative for validation.
    prompt_catalog = _cross_domain_prompt_catalog(
        question, catalog, mappings, mentioned)
    catalog_symbols = {}
    reverse_symbols = {}
    if compact_catalog:
        prompt_catalog, catalog_symbols, reverse_symbols = _compact_catalog_symbols(prompt_catalog)
    hints = property_owner_hints(question, catalog) if owner_hints else []
    # Keep mappings incident to requested domains, including possible bridge
    # domains. Never invent or automatically select a mapping for the model.
    approved_mappings = [m for m in (mappings or [])
                         if m.get('verified') is True and m.get('evidence_ids')]
    relevant_mappings = [m for m in approved_mappings
                         if not mentioned or
                         m.get('left_domain') in mentioned or
                         m.get('right_domain') in mentioned]
    mapping_catalog = [{k:v for k,v in m.items() if k in
                        ('id','left_domain','right_domain','left_property','right_property')}
                       for m in relevant_mappings]
    # Give the model a small, evidence-backed shape/connection guide on its
    # FIRST attempt. Symbols are global across domains, never domain-local.
    mapping_keys = {(m['left_domain'], m['left_property'])
                    for m in relevant_mappings} | {
                        (m['right_domain'], m['right_property'])
                        for m in relevant_mappings}
    # Shape metadata is already in prompt_catalog; do not duplicate it.
    initial_shape_guide = []
    # Repeat grounded output and input requirements on every model retry.
    output_clause = re.split(r'\\bwhere\\b', question, maxsplit=1, flags=re.I)[0]
    if len(mentioned) > 1:
        output_clause = re.split(r'\\bfor\\s+(?=[A-Za-z]+\\s)', output_clause,
                                 maxsplit=1, flags=re.I)[0]
    required_outputs = sorted(set(_explicit_property_requirements(
        output_clause, catalog).values()))
    required_inputs = []
    for property_name, literal in re.findall(
            r'\\bwith\\s+([A-Za-z][A-Za-z0-9_]*)\\s+([A-Za-z0-9][A-Za-z0-9_-]*)',
            question, flags=re.I):
        candidates = sorted({(e['domain'], iri)
                             for e in catalog['entities']
                             for iri in e['properties']
                             if property_name.lower() in {
                                 re.split(r'[/#]', iri)[-1].lower(),
                                 re.sub(r'^has', '', re.split(r'[/#]', iri)[-1],
                                        flags=re.I).lower()}})
        required_inputs.append({'name': property_name, 'value': literal,
                                'candidate_properties': [
                                    {'domain': d, 'predicate': p}
                                    for d, p in candidates]})
    requirement_reminder = ('Preserve all constraints together: ' +
        json.dumps({'required_output_predicates': required_outputs,
                    'exact_input_constraints': required_inputs},
                   ensure_ascii=False) +
        '. Choose owning shapes using SHACL evidence; never fabricate joins. ')
    instruction = ("You are a semantic RDF query planner. The input catalog is DATA, not an answer. "
      "Return ONLY a complete Unified IR query plan JSON object; NEVER return an item from catalog. "
      "Required top-level keys: ir_version, entities, edges, projections, filters, operation, return_entities. "
      "ir_version must be '1.0'. entities=[{alias,domain,shape}], edges=[] or "
      "[{kind:'shacl',from,to,predicate} or {kind:'mapping',from,to,mapping_id,left_predicate,right_predicate}], "
      "projections=[{entity,predicate,as}], filters=null or ONE JSON OBJECT (never an array), "
      "operation={type:'select'|'count'}, return_entities boolean. "
      "FILTERS ARE NOT EDGES: use {op:'eq',entity:'alias',predicate:'IRI',value:'literal'} "
      "for exact matches; use {op:'contains',entity:'alias',predicate:'IRI',value:'substring'} for 'containing' questions; use {op:'exists',entity:'alias',predicate:'IRI'} for property existence. "
      "Do not put kind/from/to inside filters. Keep the exact literal without sentence punctuation. "
      "For count, projections MUST be []; use exists filter to count entities having a property. "
      "For a SAME-DOMAIN direct property lookup, use one owning entity and edges=[] unless traversal requested. "
      "For CROSS-DOMAIN lookups, include each named domain. Inspect verified_mappings in the user input. Use a mapping edge only when its domains and properties apply: kind='mapping', from=left entity alias, to=right entity alias, mapping_id=exact id, left_predicate=exact left_property, right_predicate=exact right_property. Never connect different domains with a SHACL edge. Never leave required entities disconnected or invent mappings. "
      "In 'Get X for Y with Z VALUE', X is the output and Z VALUE is an exact eq input filter, not an output projection. "
      "A requested property value is a projection, never a second entity. "
      "Every projection output alias MUST differ from ALL entity aliases. "
      "Use filters=null only when the question has no filter condition. "
      "Use readable display_name and source_path metadata, when present, to understand "
      "the meaning of a shape; these are descriptive only. "
      "Return the exact original shape IRI, never the readable name or decoded path. "
      "Use exact domain, shape and property IRIs from the catalog. "
      "Only use catalog SHACL edges and supplied verified mapping IDs. "
      "Preserve requested domains, paths, output properties, values and filters; do not invent values. "
      "Multiple requested outputs MUST be multiple projections. "
      "For sorting use order_by=[{as:'PROJECTION_ALIAS',direction:'asc'|'desc'}]. "
      "For a requested row limit use result_limit=POSITIVE_INTEGER. "
      "Sort aliases must match projected output aliases. "
      "If no sorting or limit requested use order_by=[] and result_limit=null. "
      "If unsupported return {\"unsupported\":\"reason\"}, not a partial plan. "
      "Never return a schema entity descriptor or SHACL edge as the top-level JSON. "
      "When a question says through, via, parent, reached, or traversal, include "
      "the required parent and child entities and the verified SHACL edges between them. "
      "Do not replace a requested traversal with a direct property lookup.")
    example = {'ir_version':'1.0',
               'entities':[{'alias':'item','domain':'DOMAIN_FROM_CATALOG','shape':'SHAPE_FROM_CATALOG'}],
               'edges':[],
               'projections':[{'entity':'item','predicate':'PROPERTY_FROM_CATALOG','as':'value'}],
               'filters':None,'operation':{'type':'select'},'return_entities':False}
    # Generic mapping example; the model selects approved evidence itself.
    mapping_example = {'kind':'mapping','from':'left_entity','to':'right_entity',
                       'mapping_id':'EXACT_ID_FROM_VERIFIED_MAPPINGS',
                       'left_predicate':'EXACT_LEFT_PROPERTY_FROM_MAPPING',
                       'right_predicate':'EXACT_RIGHT_PROPERTY_FROM_MAPPING'}
    filter_example = {'op':'eq','entity':'item',
                      'predicate':'PROPERTY_FROM_CATALOG','value':'EXACT_VALUE_FROM_QUESTION'}
    count_example = dict(example, projections=[], filters={
        'op':'exists','entity':'item','predicate':'PROPERTY_FROM_CATALOG'},
        operation={'type':'count'}, return_entities=False)
    if compact_prompt:
        # Experimental shorter instructions. Full SHACL catalog and validation
        # remain authoritative; no inferred or fabricated schema entries.
        instruction = (
            "Return ONLY complete Unified IR JSON, never catalog fragments. "
            "Keys: ir_version='1.0', entities=[{alias,domain,shape}], "
            "edges=[{kind:'shacl',from,to,predicate}] or verified mapping edges, "
            "projections=[{entity,predicate,as}], filters=null or ONE object, "
            "operation={type:'select'|'count'}, return_entities=boolean. "
            "Use exact catalog domain/shape/property IRIs and verified edges only. "
            "For direct property lookup use one owning entity, edges=[], "
            "requested property as projection, filters=null unless requested. "
            "Projection aliases must differ from entity aliases. "
            "For count use projections=[] and exists filter if counting property presence. "
            "For exact filters use {op:'eq',entity:'alias',predicate:'IRI',value:'literal'}; "
            "preserve literal exactly without sentence punctuation. "
            "For traversal include all requested entities and verified edges. "
            "Preserve every requested domain, output, filter, and path. "
            "For sorting use order_by=[{as:'OUTPUT_ALIAS',direction:'asc'|'desc'}]; "
            "for requested limits use result_limit=INTEGER. "
            "Use display_name/source_path only to choose shape; output original shape IRI. "
            "If unsupported return {\"unsupported\":\"reason\"}."
        )
    instruction += ' ' + requirement_reminder
    if owner_hints:
        instruction += (' PROPERTY OWNERSHIP: for an explicitly requested property, '
                        'select an owning shape from property_owner_hints when provided; '
                        'never choose a different shape merely because it is in the '
                        'same domain. Hints are candidates, not a substitute for SHACL validation.')
    # Schema evidence for multi-projection lookups. This is prompt context only:
    # the LLM still chooses the IR, and the validator checks its choices.
    if owner_hints and not traversal_requirement(question, catalog):
        requirements = _explicit_property_requirements(question, catalog)
        requested = set(requirements.values())
        if len(requested) >= 2:
            shared_owners = [
                entity for entity in catalog['entities']
                if requested.issubset(set(entity['properties']))
            ]
            if shared_owners:
                instruction += (
                    ' MULTIPLE PROPERTY PROJECTIONS: SHACL evidence shows that '
                    'all explicitly named properties have a common owning shape. '
                    'Prefer one entity of that shape with a separate projection '
                    'for each requested property and edges=[]; do not create '
                    'separate entities for individual property values. '
                    'Evidence-backed common owner candidates: '
                    + json.dumps([
                        {'domain': owner['domain'], 'shape': owner['shape'],
                         'display_name': owner.get('display_name')}
                        for owner in shared_owners
                    ]) + '. This is schema guidance, not a precomputed plan.'
                )
            else:
                instruction += (
                    ' MULTIPLE PROPERTY PROJECTIONS: no common SHACL owning '
                    'shape was evidenced for all named properties. Never '
                    'invent a join or leave disconnected entities; use only '
                    'a supported relationship when the question requires it.'
                )
    # Give a specific no-traversal reminder only for straightforward WHERE
    # lookups whose explicitly named properties share an evidenced owner.
    # This is advisory; the model still generates the IR and SHACL validates it.
    if owner_hints and re.search(r'\\bwhere\\b', question, re.I) and not traversal_requirement(question, catalog):
        requirements = _explicit_property_requirements(question, catalog)
        if len(set(requirements.values())) >= 2:
            owners = [
                entity for entity in catalog['entities']
                if set(requirements.values()).issubset(set(entity['properties']))
            ]
            if len(owners) == 1:
                owner = owners[0]
                instruction += (
                    ' DIRECT LOOKUP WITH WHERE: the explicitly named output and '
                    'filter properties share one SHACL-evidenced owning shape. '
                    'Use ONE entity with domain=' + json.dumps(owner['domain']) +
                    ' and shape=' + json.dumps(owner['shape']) +
                    '; use edges=[]; project the requested output property and '
                    'apply the WHERE condition as a filter on that same entity. '
                    'Do not invent a relationship to represent the filter. '
                    'This guidance applies only to this direct lookup.'
                )
    if compact_catalog:
        instruction += (' Catalog shape and property IRIs are represented by S-number and P-number symbols. '
                        'Use these exact symbols in shape and predicate fields of the IR. '
                        'They will be resolved to canonical IRIs before validation. '
                        'Do not invent symbols; do not use symbols for filter values.')
        hints = [{k: catalog_symbols.get(v, v) if isinstance(v, str) else v
                  for k, v in hint.items()} for hint in hints]
    if len(mentioned) > 1:
        instruction += (
            ' Select entity shapes by matching the requested entity type to '
            'catalog display_name/source_path and checking property ownership. '
            ' Prefer explicitly named entity types with verified properties. ')
    if len(mentioned) > 1:
        instruction += (
            ' CROSS-DOMAIN RULE: each entity shape symbol is GLOBAL across '
            'all domains; never reuse the same S-number for distinct shapes. '
            'Preserve every required domain in entities on every attempt. '
            'For cross-domain joins use ONLY kind="mapping" and copy the exact '
            'mapping id and oriented predicates from verified_mappings. '
            'Never invent a mapping id or use a cross-domain SHACL edge. '
            'A mapping edge MUST connect an entity in left_domain to an '
            'entity in right_domain of that SAME verified mapping, with '
            'left_property and right_property in their documented order. '
            'Do not represent a join-key property as a separate entity unless '
            'a SHACL node shape and an actual relationship require it. '
            'Prefer the smallest connected set of evidence-backed entities '
            'that satisfies the question. ')
    messages = [{'role':'system','content':instruction},
                {'role':'user','content':json.dumps({'question':question,
                  'required_domains':sorted(mentioned), 'catalog':prompt_catalog,
                  'verified_mappings':mapping_catalog,
                  'cross_domain_edge_example_replace_all_placeholders':mapping_example,
                  'format_example_replace_all_placeholders':example,
                  'filter_ast_example':filter_example,
                  'count_ir_example':count_example,
                  **({'property_owner_hints':hints} if owner_hints else {})},
                  separators=(',', ':') if compact_prompt else None)}]
    if re.search(r'\\b(?:alphabetical|alphabetically|ascending|descending|ordered|sort(?:ed)?)\\b', question, re.I):
        messages[0]['content'] += (
            ' If the question requests sorting, populate order_by with the '
            'projected alias and correct direction.')
    if re.search(r'\\b(?:first|top|limit)\\s+\\d+\\b', question, re.I):
        messages[0]['content'] += (
            ' If the question requests a result limit, populate result_limit '
            'with the exact requested integer.')
    last_error = None
    # Keep constraints from earlier failures active across subsequent retries.
    repair_constraints = []
    for attempt in range(3):
        request_started = time.perf_counter()
        payload = {'model':model,'stream':False,'format':'json',
                   'options':{'temperature':0},'messages':messages}
        if keep_alive is not None:
            payload['keep_alive'] = keep_alive
        if prompt_diagnostics is not None:
            prompt_text = ''.join(m['content'] for m in messages)
            payload_text = json.dumps(payload, ensure_ascii=False)
            prompt_diagnostics.update({
                'attempt': attempt + 1,
                'message_count': len(messages),
                'system_characters': len(messages[0]['content']),
                'user_characters': len(messages[1]['content']),
                'prompt_characters': len(prompt_text),
                'estimated_prompt_tokens': (len(prompt_text) + 3) // 4,
                'payload_bytes': len(payload_text.encode('utf-8')),
                'model': model,
                'timeout_seconds': timeout,
                'request_status': 'started',
            })
            if prompt_diagnostics.get('path'):
                Path(prompt_diagnostics['path']).write_text(
                    json.dumps({k: v for k, v in prompt_diagnostics.items() if k != 'path'},
                               indent=2), encoding='utf-8')
        try:
            result = _request_json((ollama_host or os.getenv('OLLAMA_HOST', 'http://localhost:11434')).rstrip('/')+'/api/chat', payload, timeout)
        except (TimeoutError, URLError, HTTPError, OSError) as exc:
            # A timed-out HTTP request is still an LLM attempt. Keep it in the
            # report instead of misleadingly recording zero attempts.
            if diagnostics is not None:
                diagnostics.append({
                    'attempt': attempt + 1, 'model': model,
                    'status': 'request_failed',
                    'wall_seconds': round(time.perf_counter() - request_started, 3),
                    'error': str(exc),
                })
            if prompt_diagnostics is not None:
                prompt_diagnostics.update({
                    'request_status': 'failed',
                    'request_wall_seconds': round(time.perf_counter() - request_started, 3),
                    'request_error': str(exc),
                })
                if prompt_diagnostics.get('path'):
                    Path(prompt_diagnostics['path']).write_text(
                        json.dumps({k: v for k, v in prompt_diagnostics.items() if k != 'path'},
                                   indent=2), encoding='utf-8')
            raise
        if prompt_diagnostics is not None:
            prompt_diagnostics.update({
                'request_status': 'completed',
                'request_wall_seconds': round(time.perf_counter() - request_started, 3),
                'ollama_prompt_tokens': result.get('prompt_eval_count'),
                'ollama_generated_tokens': result.get('eval_count'),
                'ollama_prompt_eval_seconds': result.get('prompt_eval_duration', 0) / 1e9,
                'ollama_generation_seconds': result.get('eval_duration', 0) / 1e9,
            })
            if prompt_diagnostics.get('path'):
                Path(prompt_diagnostics['path']).write_text(
                    json.dumps({k: v for k, v in prompt_diagnostics.items() if k != 'path'},
                               indent=2), encoding='utf-8')
        raw = result.get('message', {}).get('content')
        attempt_record = {'attempt': attempt + 1, 'model': model, 'raw': raw,
                          'wall_seconds': round(time.perf_counter() - request_started, 3),
                          'ollama_total_seconds': result.get('total_duration', 0) / 1e9,
                          'model_load_seconds': result.get('load_duration', 0) / 1e9,
                          'prompt_eval_seconds': result.get('prompt_eval_duration', 0) / 1e9,
                          'generation_seconds': result.get('eval_duration', 0) / 1e9,
                          'prompt_tokens': result.get('prompt_eval_count'),
                          'generated_tokens': result.get('eval_count')}
        if diagnostics is not None:
            diagnostics.append(attempt_record)
        try:
            plan = normalize_single_filter(validate_planner_output(
                _resolve_catalog_symbols(json.loads(raw), reverse_symbols)))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            attempt_record['error'] = last_error
            if attempt < 2:
                messages.append({'role':'assistant','content':raw if isinstance(raw,str) else '{}'})
                messages.append({'role':'user','content':
                  'Your previous response was not a complete Unified IR query plan: ' + last_error +
                  '. Return a complete plan with all required keys, or an unsupported object. ' +
                  'For cross-domain connections use kind="mapping" with exact mapping_id, left_predicate, and right_predicate from verified_mappings; never use rdf:type, rdfs:label, or a SHACL edge as a cross-domain join. ' +
                  'Re-read the original question and preserve ALL requested projections and exact filters in the same plan. ' +
                  requirement_reminder +
                  'Do not copy an edge or entity descriptor from the catalog.'})
                continue
            raise ValueError('Model failed to generate valid Unified IR after retry: '+last_error) from exc
        try:
            check_semantic_coverage(plan, question, catalog, mentioned)
            # Coverage checks reject omitted user-requested modifiers; they do
            # not choose sort fields, directions, or limits for the LLM.
            sort_request = re.search(
                r'\\b(alphabetical(?:ly)?|ascending|descending|ordered|sort(?:ed)?)\\b',
                question, re.I)
            if sort_request and not plan.get('order_by'):
                raise ValueError('Requested ordering omitted from Unified IR')
            if sort_request and re.search(r'\\b(?:alphabetical(?:ly)?|ascending)\\b', question, re.I):
                if not any(x.get('direction') == 'asc' for x in plan.get('order_by', [])):
                    raise ValueError('Requested ascending order omitted')
            if sort_request and re.search(r'\\bdescending\\b', question, re.I):
                if not any(x.get('direction') == 'desc' for x in plan.get('order_by', [])):
                    raise ValueError('Requested descending order omitted')
            limit_request = re.search(r'\\b(?:first|top|limit)\\s+(\\d+)\\b', question, re.I)
            if limit_request and plan.get('result_limit') != int(limit_request.group(1)):
                raise ValueError('Requested result limit omitted or incorrect')
        except ValueError as exc:
            last_error = str(exc)
            attempt_record['error'] = last_error
            if attempt < 2:
                messages.append({'role':'assistant','content':raw})
                if last_error.startswith('Unrequested SHACL traversal'):
                    repair = ('Direct lookup: use exactly ONE entity that owns the '
                              'requested property, edges=[], and project the property '
                              'from that entity. A property value is not another entity. ')
                elif 'traversal omitted' in last_error.lower():
                    repair = ('Explicit traversal: include the necessary entities '
                              'and only catalog-verified SHACL edges. ')
                elif last_error.startswith('Explicit requested projection omitted:'):
                    # Provide only SHACL-backed ownership evidence to the LLM.
                    # Never alter the generated plan or invent an output property.
                    missing_predicate = last_error.split(': ', 1)[-1]
                    owners = []
                    for selected in plan['entities']:
                        for entry in catalog['entities']:
                            if (entry['domain'] == selected['domain'] and
                                    entry['shape'] == selected['shape'] and
                                    missing_predicate in entry['properties']):
                                owners.append({'entity': selected['alias'],
                                               'predicate': missing_predicate})
                    repair = (
                        'The requested output property is missing from projections '
                        'or projected from the wrong entity. The required output '
                        'predicate is ' + missing_predicate + '. '
                        'SHACL-evidenced owning entities among selected shapes: ' +
                        json.dumps(owners, ensure_ascii=False) + '. '
                        'Project the requested output from its owning entity; '
                        'do not substitute an input filter or mapping join property. '
                        'Preserve all valid mapping edges and exact input filters '
                        'from earlier attempts. If no selected entity owns the '
                        'property, choose an appropriate catalog-backed entity '
                        'rather than inventing a predicate. ')
                elif last_error.startswith('Explicit input constraint omitted:'):
                    # Give the model specific evidence from its chosen shapes.
                    # This is retry feedback only: never mutate or synthesize IR.
                    requested = re.findall(
                        r'\bwith\s+([A-Za-z][A-Za-z0-9_]*)\s+([A-Za-z0-9][A-Za-z0-9_-]*)',
                        question, flags=re.I)
                    filter_evidence = []
                    for property_name, literal in requested:
                        matches = []
                        for selected in plan['entities']:
                            for entry in catalog['entities']:
                                if (entry['domain'] != selected['domain'] or
                                        entry['shape'] != selected['shape']):
                                    continue
                                for iri in entry['properties']:
                                    local = re.split(r'[/#]', iri)[-1].lower()
                                    names = {local}
                                    if local.startswith('has') and len(local) > 3:
                                        names.add(local[3:])
                                    if property_name.lower() in names:
                                        matches.append({'entity': selected['alias'],
                                                        'predicate': iri, 'value': literal})
                        if len(matches) == 1:
                            filter_evidence.append(matches[0])
                    if plan.get('filters') is None:
                        problem = 'The previous plan has filters=null. '
                    else:
                        problem = ('The previous filter is absent or uses the wrong '
                                   'entity, predicate, operator, or literal. ')
                    repair = (
                        problem +
                        'A cross-domain mapping edge joins entities using its '
                        'left_predicate and right_predicate; those are NOT '
                        'automatically the predicates for question filters. '
                        'For cross-domain queries use kind=mapping, an exact approved mapping_id, and the exact left_predicate/right_predicate from verified_mappings; never use kind=shacl between domains. '
                        'Preserve valid mapping edges, but independently select '
                        'the requested input filter property from the owning '
                        'entity shape. Use op=eq and preserve the exact literal. '
                        'Unambiguous SHACL property evidence for this question: ' +
                        json.dumps(filter_evidence, ensure_ascii=False) + '. '
                        'Do not substitute a mapping join predicate for an '
                        'input filter predicate. ')
                else:
                    repair = ('Preserve explicitly requested projections, filters, '
                              'and literal values; do not invent traversals. ')
                if repair not in repair_constraints:
                    repair_constraints.append(repair)
                messages.append({'role':'user','content':
                    'Your previous IR failed semantic coverage: ' + last_error +
                    '. ALL constraints from prior failures remain mandatory: ' +
                    ' '.join(repair_constraints) +
                    'Every projection alias MUST differ from every entity alias. '
                    'Regenerate the COMPLETE unified IR using catalog-backed '
                    'shapes and properties, or return {"unsupported":"reason"}.'})
                continue
            raise ValueError('Semantic coverage failure after retries: '+last_error) from exc
        # Check full SHACL evidence BEFORE accepting a model plan. This is part of
        # the model retry loop, not a downstream one-shot compiler failure.
        try:
            plan = resolve_shapes(plan, index, mappings=mappings)
        except (ValueError, KeyError, TypeError) as exc:
            last_error = str(exc)
            attempt_record['error'] = last_error
            if attempt < 2:
                # Supply concrete schema candidates after a bad shape choice.
                # This is evidence for the model, never an automatic IR repair.
                shape_evidence = ''
                if ('Entity shape not present' in last_error
                        or 'Property lacks unique SHACL evidence' in last_error):
                    # Show candidates for EVERY requested domain, not only
                    # owners of the output property. Cross-domain inputs may
                    # own the mapping key but not the projected property.
                    candidates = []
                    mapping_properties = {
                        (m['left_domain'], m['left_property'])
                        for m in relevant_mappings
                    } | {
                        (m['right_domain'], m['right_property'])
                        for m in relevant_mappings
                    }
                    for domain in sorted(mentioned):
                        domain_shapes = [e for e in catalog['entities']
                                         if e['domain'] == domain]
                        ranked = sorted(
                            domain_shapes,
                            key=lambda e: (
                                -sum(p in required_outputs or
                                     (domain, p) in mapping_properties
                                     for p in e['properties']),
                                e['shape']))
                        for e in ranked[:8]:
                            candidates.append({
                                'domain': domain,
                                'shape': (catalog_symbols.get(e['shape'], e['shape'])
                                          if compact_catalog else e['shape']),
                                'relevant_properties': [
                                    (catalog_symbols.get(p, p)
                                     if compact_catalog else p)
                                    for p in e['properties']
                                    if p in required_outputs
                                    or (domain, p) in mapping_properties],
                            })
                    shape_evidence = (
                        ' SHACL-backed candidates for EACH required domain '
                        '(select an owning shape; do not omit domains): ' +
                        json.dumps(candidates, ensure_ascii=False) +
                        '. Verified mapping candidates (copy exact ID, '
                        'endpoint order and predicates): ' +
                        json.dumps(mapping_catalog, ensure_ascii=False) + '. ')
                messages.append({'role':'assistant','content':raw})
                messages.append({'role':'user','content':
                    'The previous IR failed SHACL validation: ' + last_error + '. ' +
                    (' A mapping edge must connect the verified left_domain '
                     'to right_domain, never two entities from the same '
                     'domain. Remove any unsupported intermediate entity '
                     'and its invalid edge; keep the valid cross-domain '
                     'mapping and all explicitly requested entities. '
                     if 'Mapping evidence does not match edge' in last_error
                     else '') +
                    shape_evidence +
                    'For CROSS-DOMAIN queries, examine verified_mappings in the original user message. A SHACL edge must not connect entities in different domains. When a verified mapping applies, use an edge with kind="mapping", from and to set to the corresponding entity aliases, mapping_id set to the exact verified mapping id, and left_predicate and right_predicate copied exactly from its left_property and right_property. Every entity must be connected by valid edges; do not solve a cross-domain SHACL error by removing the edge. Never invent or approve a mapping. ' +
                    '. If the error mentions filter: filters MUST be a single object, NOT a list; '
                    'use {"op":"eq","entity":"ALIAS","predicate":"PROPERTY_IRI","value":"EXACT_LITERAL"}. '
                    'Never put a SHACL edge with kind/from/to into filters. '
                    'Preserve exact literal text without trailing sentence punctuation. '
                    'Projection output aliases MUST differ from every entity alias; '
                    'use an entity alias such as instrument and a separate output alias '
                    'such as measured_variable. '
                    'ALL prior semantic constraints remain mandatory: ' +
                    ' '.join(repair_constraints) +
                    'If the error says Property lacks unique SHACL evidence, '
                    'the requested source shape is WRONG for that property. '
                    'Choose the owning entity shape from matching source shapes '
                    'listed in the error, preserving the requested predicate; '
                    'do not add a traversal or an unrequested filter. '
                    'If the question has no WHERE clause and requests a direct '
                    'SELECT property lookup, use filters=null. '
                    'If the error mentions COUNT: set projections=[] and operation={"type":"count"}; '
                    'use a supported exists filter to require a property. '
                    'For every shacl edge, use the exact from_shape and to_shape '
                    'shown on ONE shacl_edges catalog record with matching domain '
                    'and predicate. The source entity MUST use from_shape; the target '
                    'entity MUST use to_shape. Do not invent or change predicates. '
                    'Preserve requested projections on their correct entity. '
                    'Return the complete corrected IR or unsupported.'})
                continue
            raise ValueError('SHACL validation failed after model retries: '+last_error) from exc
        attempt_record['status'] = 'accepted'
        return plan
    raise ValueError('Model failed to generate Unified IR: '+str(last_error))


def execute_select(sparql, endpoint, timeout=60):
    # POST as application/sparql-query, read-only SELECT enforced by compiler.
    req = Request(endpoint, data=sparql.encode('utf-8'),method='POST',
                  headers={'Content-Type':'application/sparql-query',
                           'Accept':'application/sparql-results+json'})
    with urlopen(req,timeout=timeout) as response: return json.load(response)


def main():
    parser=argparse.ArgumentParser(description='Experimental Qwen → unified IR → SHACL validation → SPARQL → GraphDB')
    parser.add_argument('command',choices=['answer','compile'])
    parser.add_argument('--schema',required=True)
    parser.add_argument('--question')
    parser.add_argument('--ir',help='Existing unified IR JSON; bypass Qwen')
    parser.add_argument('--mappings',help='Independently verified mapping registry JSON')
    parser.add_argument('--endpoint',help='GraphDB SPARQL endpoint; optional for compile')
    parser.add_argument('--ollama-host',default=os.getenv('OLLAMA_HOST', 'http://localhost:11434'))
    parser.add_argument('--model',default='qwen2.5-coder:3b')
    parser.add_argument('--owner-hints',action='store_true',
                        help='Opt-in evidence-backed property owning shape hints')
    parser.add_argument('--compact-catalog',action='store_true',
                        help='Experimental lossless SHACL IRI symbol compression')
    parser.add_argument('--compact-prompt',action='store_true',
                        help='Experiment with shorter planner instructions (opt-in)')
    parser.add_argument('--keep-alive',default=None,
                        help='Ollama model residency, e.g. 30m (default: Ollama setting)')
    parser.add_argument('--llm-timeout',type=int,default=120,
                        help='Ollama HTTP timeout per planning attempt in seconds (default: 120)')
    parser.add_argument('--graph-mode',choices=['default','all_named','selected'],default='all_named')
    parser.add_argument('--graph-iri')
    parser.add_argument('--include-graph',action='store_true')
    parser.add_argument('--limit',type=int,default=100)
    parser.add_argument('--output',help='Write full JSON report to file')
    parser.add_argument('--prompt-diagnostics',help='Write prompt-size and request timing diagnostics JSON (no prompt text)')
    args=parser.parse_args()
    if args.llm_timeout < 1: parser.error('--llm-timeout must be positive')
    if not args.ir and not args.question: parser.error('Provide --ir or --question')
    if args.command=='answer' and not args.endpoint: parser.error('answer requires --endpoint')
    registry=json.loads(Path(args.mappings).read_text(encoding='utf-8')) if args.mappings else None
    timings={}
    stage_started=time.perf_counter()
    try:
        diagnostics=[]
        prompt_diagnostics={'path': args.prompt_diagnostics} if args.prompt_diagnostics else None
        plan=json.loads(Path(args.ir).read_text(encoding='utf-8')) if args.ir else generate_ir(
            args.question,args.schema,model=args.model,ollama_host=args.ollama_host,
            timeout=args.llm_timeout,mappings=registry,diagnostics=diagnostics,
            compact_prompt=args.compact_prompt,keep_alive=args.keep_alive,
            owner_hints=args.owner_hints,prompt_diagnostics=prompt_diagnostics,
            compact_catalog=args.compact_catalog)
        timings['planning_seconds']=round(time.perf_counter()-stage_started,3)
        stage_started=time.perf_counter()
        query=compile_graph_ir(plan,args.schema,mappings=registry,graph_mode=args.graph_mode,
                               graph_iri=args.graph_iri,include_graph=args.include_graph,limit=args.limit)
        timings['compilation_seconds']=round(time.perf_counter()-stage_started,3)
        result={'status':'compiled','ir':plan,'sparql':query,'planning_attempts':diagnostics}
        if args.command=='answer':
            stage_started=time.perf_counter()
            try:
                result['results']=execute_select(query,args.endpoint)
            finally:
                timings['graphdb_seconds']=round(time.perf_counter()-stage_started,3)
            result['status']='executed'
    except (ValueError,HTTPError,URLError,TimeoutError,OSError,KeyError,TypeError) as exc:
        result={'status':'rejected_or_failed','error':str(exc),
                'planning_attempts':locals().get('diagnostics', [])}
    result['timings']=timings
    output=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output: Path(args.output).write_text(output,encoding='utf-8')
    print(output)
    if result['status']=='rejected_or_failed': raise SystemExit(1)

if __name__=='__main__': main()
