"""Opt-in DTwise unified IR end-to-end CLI; never modifies existing main.py."""
import os
import argparse
import base64
import binascii
import json
import re
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
    output_names = _explicit_property_requirements(before_where[0], catalog)
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
    # Enforce explicitly requested query operations before accepting a plan.
    lower_question = question.lower()
    operation = plan.get('operation', {})
    numbers = {'one':1,'two':2,'three':3,'four':4,'five':5,
               'six':6,'seven':7,'eight':8,'nine':9,'ten':10}
    def quantity(token):
        return int(token) if token.isdigit() else numbers.get(token)
    if re.search(r'\b(?:for each|per)\b', lower_question) and re.search(r'\bcount\b', lower_question):
        if operation.get('type') != 'count' or not operation.get('group_by'):
            raise ValueError('Requested grouped COUNT omitted')
    threshold_match = re.search(r'\bmore than\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b', lower_question)
    if threshold_match and re.search(r'\bsignalmappings?\b', lower_question):
        threshold = quantity(threshold_match.group(1))
        having = operation.get('having')
        if operation.get('type') != 'count' or not operation.get('group_by') or having != {'op':'gt','value':threshold}:
            raise ValueError('Requested HAVING threshold omitted')
    # Aggregate questions must group by the explicitly named catalog property.
    # In particular, "AssetIdentifiers with more than three SignalMappings"
    # groups on hasAssetIdentifier, not the hasSignalMapping relationship.
    if operation.get('type') == 'count' and operation.get('group_by'):
        group_aliases = set(operation['group_by'])
        group_projections = [p for p in plan['projections']
                             if p.get('as') in group_aliases]
        grouping_text = re.search(
            r'\b(?:for each|per)\s+([A-Za-z][A-Za-z0-9_]*)', question, re.I)
        if grouping_text is None and threshold_match:
            grouping_text = re.search(
                r'\b(?:list|show|get|which)\s+([A-Za-z][A-Za-z0-9_]*)',
                question, re.I)
        if grouping_text:
            name = grouping_text.group(1).lower()
            # Resolve plural surface forms only when the property match is unique.
            candidates = set()
            for catalog_entity in catalog['entities']:
                for predicate in catalog_entity['properties']:
                    local = re.split(r'[/#]', predicate)[-1].lower()
                    names = {local}
                    if local.startswith('has') and len(local) > 3:
                        names.add(local[3:])
                    if any(n == name or n + 's' == name or
                           (n.endswith('s') and n + 'es' == name)
                           for n in names):
                        candidates.add(predicate)
            if len(candidates) == 1:
                expected = next(iter(candidates))
                if not any(p.get('predicate') == expected for p in group_projections):
                    raise ValueError('Requested grouping property omitted: ' + expected)
    if re.search(r'\b(?:alphabetical|alphabetically)\b', lower_question):
        if not any(x.get('direction') == 'asc' for x in plan.get('order_by', []) if isinstance(x, dict)):
            raise ValueError('Requested alphabetical ORDER BY omitted')
    first = re.search(r'\bfirst\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b', lower_question)
    if first and plan.get('limit') != quantity(first.group(1)):
        raise ValueError('Requested LIMIT omitted')
    # A direct SELECT property lookup without a WHERE clause must not invent
    # a literal filter. COUNT/relationship questions may legitimately use
    # property-existence constraints without an explicit WHERE.
    if (len(before_where) == 1 and output_names and
            plan['operation']['type'] == 'select' and
            not traversal_requirement(question, catalog) and
            plan.get('filters') is not None):
        raise ValueError('Unrequested filter in direct property lookup')
    # An unrequested traversal cannot be added to a simple property lookup.
    # Leave traversals allowed when the question actually requests a relationship.
    if not traversal_requirement(question, catalog) and not re.search(
            r'\b(?:relationship|related|connected|link(?:ed)?|join)\b', question, re.I):
        if output_names and plan['edges']:
            raise ValueError('Unrequested SHACL traversal in direct property lookup')
    return plan

def generate_ir(question, schema, *, model='qwen2.5-coder:3b',
                ollama_host=None, timeout=120, mappings=None, diagnostics=None):
    index = json.loads(Path(schema).read_text(encoding='utf-8'))
    full_catalog = catalog_from_schema(index)
    catalog, mentioned = _focused_catalog(full_catalog, question)
    # Prefer the legacy SHACL projection/join discovery for explicitly named
    # cross-domain questions. It may only emit a mapping edge when the caller
    # supplies independently verified identity evidence; never infer approval.
    if len(mentioned) >= 2:
        from .legacy_join_adapter import plan_legacy_projection_ir
        legacy_ir = plan_legacy_projection_ir(question, schema, mappings)
        if legacy_ir is not None:
            if diagnostics is not None:
                diagnostics.append({'planner': 'legacy_shacl_projection_adapter',
                                    'status': 'accepted', 'model': None})
            return legacy_ir
    mapping_catalog = [{k:v for k,v in m.items() if k in
                        ('id','left_domain','right_domain','left_property','right_property')}
                       for m in (mappings or []) if m.get('verified') is True and m.get('evidence_ids')]
    instruction = ("You are a semantic RDF query planner. The input catalog is DATA, not an answer. "
      "Return ONLY a complete Unified IR query plan JSON object; NEVER return an item from catalog. "
      "Required top-level keys: ir_version, entities, edges, projections, filters, operation, return_entities. "
      "ir_version must be '1.0'. entities=[{alias,domain,shape}], edges=[] or "
      "[{kind:'shacl',from,to,predicate} or {kind:'mapping',from,to,mapping_id,left_predicate,right_predicate}], "
      "projections=[{entity,predicate,as}], filters=null or ONE JSON OBJECT (never an array), "
      "operation={type:'select'|'count'}, return_entities boolean. "
      "FILTERS ARE NOT EDGES: use {op:'eq',entity:'alias',predicate:'IRI',value:'literal'} "
      "for exact matches; use {op:'exists',entity:'alias',predicate:'IRI'} for property existence. "
      "Do not put kind/from/to inside filters. Keep the exact literal without sentence punctuation. "
      "For a global count, projections=[] and operation={type:'count'}; use an exists filter to count entities having a property. "
      "For COUNT per property, projections=[{entity,predicate,as:'group_key'}], "
      "operation={type:'count',group_by:['group_key']}; group_by MUST be nested INSIDE operation, NEVER top-level. "
      "Copy no placeholder strings from examples: all domain, shape and predicate values MUST be real catalog values. "
      "For counts above N add operation.having={op:'gt',value:N} (integer). "
      "An aggregate threshold belongs ONLY in operation.having, NEVER in filters. "
      "For grouped counts, group by the requested grouping PROPERTY, not by a relationship named after the counted entity. "
      "For pure grouped aggregation use filters=null and return_entities=false. "
      "For alphabetical ordering add order_by=[{by:'projected_alias',direction:'asc'}]. "
      "For first N results add top-level limit=N. "
      "For SELECT with ordering, preserve the requested projected output. "
      "For a direct property lookup, grouped count, or ordered property listing, use exactly one owning entity and edges=[] unless a traversal is explicitly requested. "
      "Do NOT include Server or other unrelated entities in a SignalMapping property query. "
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
      "If unsupported return {\"unsupported\":\"reason\"}, not a partial plan. "
      "Never return a schema entity descriptor or SHACL edge as the top-level JSON. "
      "When a question says through, via, parent, reached, or traversal, include "
      "the required parent and child entities and the verified SHACL edges between them. "
      "Do not replace a requested traversal with a direct property lookup.")
    # Structural examples with fake identifiers caused small models to copy
    # DOMAIN_FROM_CATALOG / PROPERTY_IRI verbatim. Supply only actual evidence.
    properties = _explicit_property_requirements(question, catalog)
    catalog_hints = []
    for entity in catalog['entities']:
        for predicate in entity['properties']:
            if predicate in properties.values():
                catalog_hints.append({'domain': entity['domain'],
                                      'shape': entity['shape'],
                                      'predicate': predicate})
    messages = [{'role':'system','content':instruction},
                {'role':'user','content':json.dumps({
                    'question':question,
                    'required_domains':sorted(mentioned),
                    'catalog':catalog,
                    'explicit_property_candidates':catalog_hints[:24],
                    'verified_mappings':mapping_catalog,
                    'required_ir_structure':{
                        'ir_version':'1.0',
                        'entities':'list of catalog-backed {alias,domain,shape}',
                        'edges':'[] for direct property queries',
                        'projections':'list of {entity,predicate,as}',
                        'filters':'null or filter object',
                        'operation':'{type:count,group_by:[projection alias]} for grouped count; otherwise {type:select}',
                        'return_entities':'boolean'
                    },
                    'never_copy_structure_descriptions_as_values':True
                })}]
    last_error = None
    # Keep constraints from earlier failures active across subsequent retries.
    repair_constraints = []
    for attempt in range(3):
        result = _request_json((ollama_host or os.getenv('OLLAMA_HOST', 'http://localhost:11434')).rstrip('/')+'/api/chat', {
            'model':model,'stream':False,'format':'json','options':{'temperature':0},
            'messages':messages}, timeout)
        raw = result.get('message', {}).get('content')
        attempt_record = {'attempt': attempt + 1, 'model': model, 'raw': raw}
        if diagnostics is not None:
            diagnostics.append(attempt_record)
        try:
            plan = normalize_single_filter(validate_planner_output(json.loads(raw)))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            attempt_record['error'] = last_error
            if attempt < 2:
                messages.append({'role':'assistant','content':raw if isinstance(raw,str) else '{}'})
                messages.append({'role':'user','content':
                  'Your previous response was not a complete Unified IR query plan: ' + last_error +
                  '. Return a complete plan with all required keys, or an unsupported object. ' +
                  'Do not copy an edge or entity descriptor from the catalog.'})
                continue
            raise ValueError('Model failed to generate valid Unified IR after retry: '+last_error) from exc
        try:
            check_semantic_coverage(plan, question, catalog, mentioned)
        except ValueError as exc:
            last_error = str(exc)
            attempt_record['error'] = last_error
            if attempt < 2:
                messages.append({'role':'assistant','content':raw})
                if last_error.startswith('Unrequested SHACL traversal'):
                    repair = ('Direct lookup: use exactly ONE entity that owns the '
                              'requested property, edges=[], and project the property '
                              'from that entity. A property value is not another entity. ')
                elif 'grouped COUNT omitted' in last_error:
                    repair = ('The query asks for grouped aggregation. Use '
                              'operation={"type":"count","group_by":["group_key"]}, '
                              'and project the grouping property with as="group_key". '
                              'group_by MUST be INSIDE operation, not top-level. '
                              'Use real domain/shape/predicate from the catalog, '
                              'never *_FROM_CATALOG placeholders. ')
                elif 'Requested grouping property omitted' in last_error:
                    repair = ('Group by the explicitly requested property IRI shown in the error. '
                              'Use the entity shape that OWNS that property, not a similarly named '
                              'relationship property. For AssetIdentifier, project hasAssetIdentifier '
                              'from SignalMapping and group_by its projection alias. '
                              'Use edges=[], filters=null, and retain operation.having. ')
                elif 'HAVING threshold omitted' in last_error:
                    repair = ('Use operation={"type":"count","group_by":["group_key"],'
                              '"having":{"op":"gt","value":3}} with real catalog properties. '
                              'Set filters=null: the count threshold belongs ONLY in operation.having, '
                              'not in a property-level gt filter. Use one owning entity and edges=[]. ')
                elif 'ORDER BY omitted' in last_error or 'LIMIT omitted' in last_error:
                    repair = ('For alphabetical first ten results, use '
                              'order_by=[{"by":"value","direction":"asc"}], '
                              'limit=10 and project the requested catalog property as value. '
                              'Include ONLY the entity owning that property; edges=[] and '
                              'return_entities=false. Do not include an unrelated Server. ')
                elif 'traversal omitted' in last_error.lower():
                    repair = ('Explicit traversal: include the necessary entities '
                              'and only catalog-verified SHACL edges. ')
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
                messages.append({'role':'assistant','content':raw})
                shacl_repair = ''
                if 'Unsupported filter operator' in last_error and plan.get('operation', {}).get('having'):
                    shacl_repair = ('The aggregate comparison is already in operation.having. '
                                    'REMOVE the invalid gt filter entirely: set filters=null. '
                                    'Preserve operation.group_by and operation.having. ')
                if 'Disconnected query graph' in last_error and not traversal_requirement(question, catalog):
                    shacl_repair += ('Direct property request: REMOVE unrelated entities; '
                                     'keep exactly the property-owning entity, edges=[], '
                                     'and return_entities=false. Preserve order_by and limit. ')
                messages.append({'role':'user','content':
                    'The previous IR failed SHACL validation: ' + last_error + '. ' + shacl_repair +
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
                    'For GLOBAL COUNT only, set projections=[] and operation={"type":"count"}; '
                    'for GROUPED COUNT keep the grouping projection, operation.group_by, '
                    'and operation.having when requested. '
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
    parser.add_argument('--llm-timeout',type=int,default=120,
                        help='Ollama HTTP timeout per planning attempt in seconds (default: 120)')
    parser.add_argument('--graph-mode',choices=['default','all_named','selected'],default='all_named')
    parser.add_argument('--graph-iri')
    parser.add_argument('--include-graph',action='store_true')
    parser.add_argument('--limit',type=int,default=100)
    parser.add_argument('--output',help='Write full JSON report to file')
    args=parser.parse_args()
    if args.llm_timeout < 1: parser.error('--llm-timeout must be positive')
    if not args.ir and not args.question: parser.error('Provide --ir or --question')
    if args.command=='answer' and not args.endpoint: parser.error('answer requires --endpoint')
    registry=json.loads(Path(args.mappings).read_text(encoding='utf-8')) if args.mappings else None
    try:
        diagnostics=[]
        plan=json.loads(Path(args.ir).read_text(encoding='utf-8')) if args.ir else generate_ir(
            args.question,args.schema,model=args.model,ollama_host=args.ollama_host,
            timeout=args.llm_timeout,mappings=registry,diagnostics=diagnostics)
        query=compile_graph_ir(plan,args.schema,mappings=registry,graph_mode=args.graph_mode,
                               graph_iri=args.graph_iri,include_graph=args.include_graph,limit=args.limit)
        result={'status':'compiled','ir':plan,'sparql':query,'planning_attempts':diagnostics}
        if args.command=='answer':
            result['results']=execute_select(query,args.endpoint)
            result['status']='executed'
    except (ValueError,HTTPError,URLError,TimeoutError,OSError,KeyError,TypeError) as exc:
        result={'status':'rejected_or_failed','error':str(exc),
                'planning_attempts':locals().get('diagnostics', [])}
    output=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output: Path(args.output).write_text(output,encoding='utf-8')
    print(output)
    if result['status']=='rejected_or_failed': raise SystemExit(1)

if __name__=='__main__': main()
