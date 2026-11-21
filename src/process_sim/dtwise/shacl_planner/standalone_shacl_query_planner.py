"""Standalone SHACL-grounded, one-Qwen-call query-plan experiment.

Phase 1 v6: SELECT, simple filters, AND/OR, derived sibling JOIN, ungrouped COUNT,
ORDER BY, LIMIT. Phase-2 constructs are explicitly unsupported.
No SPARQL generation or execution. Dry-run still uses Ollama embeddings.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

repo_src = Path.cwd() / 'src'
if repo_src.is_dir():
    sys.path.insert(0, str(repo_src))
from process_sim.dtwise.shacl_planner.grounding.subgraph import load_index, extract_question
from process_sim.dtwise.experimental_shacl_candidates import prepare_candidates
from process_sim.dtwise.experimental_shacl_qualified_candidates import qualify_candidates
from process_sim.dtwise.experimental_shacl_ollama import ollama_select
from process_sim.dtwise.shacl_planner.semantic_candidates import semantic_candidates
from process_sim.dtwise.shacl_planner.multi_domain.domain_resolution import (
    resolve_domain, resolve_domains, DomainResolutionError,
)

SYSTEM_PROMPT = """You are a SHACL-grounded Phase-1 query planner. Return ONE JSON object, no prose.
Only use candidate IDs supplied in the question. Never invent paths or literal values.
Every referenced concept must be explicitly named in the question (case-insensitive, simple plural allowed). Do not infer synonyms.
A concept may have multiple verified paths: choose the path under the explicitly named owner, or abstain when ambiguous.
When returning a named property value, project its P (property) candidate, not R (result) candidates.
The same property name may belong to multiple concepts: select only the SHACL-verified
property directly owned by the requested concept. Do not select descendant or unrelated
owners merely because their properties have the same name. If ownership is ambiguous,
return ambiguous or unresolved; never project all matching paths.
Supported: SELECT entity/property retrieval; simple comparisons (= != > >= < <=);
AND/OR between filters; same-owner sibling branch JOIN; simple COUNT of entities;
ORDER BY ASC/DESC on a grounded property; LIMIT. All other query operations
(including GROUP BY, HAVING, SUM, AVG, MIN, MAX, DISTINCT, OFFSET, ASK,
OPTIONAL, UNION, MINUS, subqueries, CONSTRUCT, DESCRIBE, UPDATE) are unsupported.
If the question requests any unsupported operation, set status=unsupported and
return empty plan fields. Never silently omit an unsupported clause.
projection_ids are only values/entities to RETURN; existence_ids are required
concept paths not returned. Endpoint addresses require Address property projections.
A Device with both endpoint types projects Device and requires both sibling
EndPoint and PLCEndPoint paths under the SAME Device, not Symbol.
Parent-child traversal is not a sibling JOIN. Python computes JOIN from
verified SHACL topology; always output join=false and join_owner_id=null.
boolean_operator describes FILTER combinations ONLY; NONE for 0 or 1 filters.
COUNT is only ungrouped COUNT of a grounded result concept, with count_target_id.
Do not add sorting, LIMIT, COUNT, or filters unless requested. For a vague or non-exact
property name, return ambiguous. LIMIT is supported (including first N).
When a necessary candidate is missing, return unresolved. If a clause cannot
be represented, return unsupported. join_owner_id is ALWAYS null; Python derives it.
Return EXACTLY these keys, using null/[] for unused fields:
{
 "status":"selected|ambiguous|unresolved|unsupported",
 "projection_ids":["R1"],
 "existence_ids":[],
 "filters":[{"property_id":"P1","operator":"=","value":"literal"}],
 "boolean_operator":"NONE",
 "join":false,
 "count_target_id":null,
 "order_by":[{"property_id":"P1","direction":"ASC"}],
 "limit":null,
 "join_owner_id":null,
 "reason":"brief explanation"
}
For unsupported/ambiguous/unresolved return empty projections/existence/filters/order_by,
count_target_id=null, limit=null, boolean_operator=NONE, join=false.
"""

DEFAULT_QUESTIONS = [
  "Show all Device records.",
  "Show all devices.",
  "Show Device where DeviceType is Sensor.",
  "Show Device where DeviceType is Sensor AND AssetIdentifier is FI_101.",
  "Show Device where DeviceType is Sensor OR AssetIdentifier is FI_101.",
  "Show Device and its EndPoint.",
  "Show EndPoint and PLCEndPoint belonging to the same Device.",
  "Show Address of EndPoint and PLCEndPoint for Device where DeviceType is Sensor.",
  "Show Device with both EndPoint and PLCEndPoint where AssetIdentifier is FI_101.",
  "Count Device.",
  "List Device ordered by DeviceType ascending.",
  "List Device ordered by DeviceType descending, limit 10.",
  "Show the first 5 Device.",
  "Show equipment.",
  "Show connection points.",
  "Show Device where Status is Active.",
  "Count Device grouped by DeviceType.",
  "Show Device where DeviceType is Sensor and return the first 3 results."
]

OPS = {'=', '!=', '>', '>=', '<', '<='}
OPERATION_REGISTRY = {
 'supported': ['SELECT','FILTER','AND','OR','shared-owner JOIN','COUNT (ungrouped)',
               'ORDER BY ASC/DESC','LIMIT'],
 'phase_2': ['GROUP BY','HAVING','SUM','AVG','MIN','MAX','SAMPLE','GROUP_CONCAT',
             'DISTINCT','OFFSET','ASK','OPTIONAL','UNION','MINUS','EXISTS','BIND',
             'VALUES','subqueries','GRAPH','SERVICE','CONSTRUCT','DESCRIBE','UPDATE']
}


def validate_output(answer, offered):
    errors=[]
    if not isinstance(answer,dict): return ['Response must be JSON object']
    required={'status','projection_ids','existence_ids','filters','boolean_operator',
              'join','count_target_id','order_by','limit','join_owner_id','reason'}
    if set(answer)!=required: errors.append('Expected exactly Phase-1 keys')
    status=answer.get('status')
    if status not in {'selected','ambiguous','unresolved','unsupported'}:
        errors.append('Invalid status')
    lookup={c['id']:c for c in offered}
    props={k for k,c in lookup.items() if c['kind']=='property'}
    results={k for k,c in lookup.items() if c['kind']=='result'}
    for field,allowed in [('projection_ids',props|results),('existence_ids',results)]:
        v=answer.get(field)
        if not isinstance(v,list) or any(not isinstance(x,str) or x not in allowed for x in v):
            errors.append(f'Invalid {field}')
        elif len(v)!=len(set(v)): errors.append(f'Duplicate {field}')
    filters=answer.get('filters')
    if not isinstance(filters,list): errors.append('Invalid filters');filters=[]
    for i,f in enumerate(filters):
        if not isinstance(f,dict) or set(f)!={'property_id','operator','value'} or \
           f.get('property_id') not in props or f.get('operator') not in OPS or \
           not isinstance(f.get('value'),str) or not f['value'].strip():
            errors.append(f'Invalid filter {i}')
    if answer.get('boolean_operator') not in {'NONE','AND','OR'}:
        errors.append('Invalid boolean_operator')
    if type(answer.get('join')) is not bool: errors.append('join must be boolean')
    count=answer.get('count_target_id')
    if count is not None and count not in results: errors.append('COUNT target must be offered result ID')
    order=answer.get('order_by')
    if not isinstance(order,list): errors.append('Invalid order_by');order=[]
    for i,o in enumerate(order):
        if not isinstance(o,dict) or set(o)!={'property_id','direction'} or \
           o.get('property_id') not in props or o.get('direction') not in {'ASC','DESC'}:
            errors.append(f'Invalid order_by {i}')
    limit=answer.get('limit')
    if limit is not None and (type(limit) is not int or limit<=0):
        errors.append('LIMIT must be positive integer')
    if answer.get('join_owner_id') is not None: errors.append('join_owner_id must be null')
    if not isinstance(answer.get('reason'),str) or not answer['reason'].strip():
        errors.append('Nonempty reason required')
    if status=='selected':
        if len(filters)<2 and answer.get('boolean_operator')!='NONE':
            errors.append('Boolean operator requires >=2 filters')
        if len(filters)>=2 and answer.get('boolean_operator')=='NONE':
            errors.append('Multiple filters require Boolean operator')
        if not (answer.get('projection_ids') or count):
            errors.append('Selected plan needs projection or COUNT')
        if count is not None and answer.get('projection_ids'):
            errors.append('Simple COUNT cannot also project ungrouped fields')
    else:
        if any((answer.get('projection_ids'),answer.get('existence_ids'),filters,order,
                count is not None,limit is not None,answer.get('join') is True,
                answer.get('boolean_operator')!='NONE')):
            errors.append('Nonselected plan must not contain partial query')
    return errors


def _paths(offered):
    return {c['id']: tuple(c.get('node_uris') or ()) for c in offered}


def _prefix(a,b):
    return len(a)<=len(b) and a==b[:len(a)]


def _deepest_owner(paths, offered):
    """Return meaningful shared-owner candidate, excluding domain-only roots."""
    if len(paths)<2 or any(not p for p in paths):
        return None,False,{'reason':'Fewer than two grounded paths'}
    common=list(paths[0])
    for path in paths[1:]:
        i=0
        while i<min(len(common),len(path)) and common[i]==path[i]: i+=1
        common=common[:i]
    # Require a meaningful owner BELOW the domain root (e.g. ECAD -> Device).
    if len(common)<2:
        return None,False,{'reason':'Only domain root is shared; no same-entity owner'}
    branches={p[len(common)] for p in paths if len(p)>len(common)}
    branch_join=len(branches)>1
    candidates=[c['id'] for c in offered if c['kind']=='result'
                and tuple(c.get('node_uris') or ())==tuple(common)]
    return (candidates[0] if candidates else None),branch_join,{
        'shared_depth':len(common),'branch_count':len(branches),
        'owner_candidate_found':bool(candidates)}


def _constraint_literals(question):
    """Diagnostic-only value coverage; no question-specific templates."""
    values=[]
    patterns=[r'\bwhere\s+[\w]+\s+(?:is|equals|equal\s+to)\s+([\w.-]+)',
              r'\b(?:AND|OR)\s+[\w]+\s+(?:is|equals|equal\s+to)\s+([\w.-]+)',
              r'\b(?:identified|classified)\s+as\s+([\w.-]+)']
    for pattern in patterns:
        for match in re.finditer(pattern,question,re.I):
            v=match.group(1).rstrip('.,;?!')
            if v.casefold() not in {'same','both','all','their','the','a'} and v not in values:
                values.append(v)
    return values


def _unsupported_intent(question):
    """Conservative gate for Phase-2 features; Qwen also classifies unsupported intent."""
    patterns={
      'GROUP BY':r'\b(group(?:ed|ing)?\s+by|per\s+\w+\s+type)\b',
      'HAVING':r'\bhaving\b',
      'SUM/AVG/MIN/MAX':r'\b(sum|average|avg|minimum|maximum|min|max|total\s+(?:of|value))\b',
      'DISTINCT':r'\b(distinct|unique)\b',
      'OFFSET':r'\b(offset|skip\s+(?:the\s+)?first|skip\s+\d+)\b',
      'ASK':r'^(?:are there|is there|do any|does any)\b',
      'OPTIONAL/UNION/MINUS':r'\b(optional|union|minus)\b',
      'EXISTS/BIND/VALUES':r'\b(not\s+exists|exists|bind)\b|\bVALUES\s*\{',
      'CONSTRUCT/DESCRIBE':r'\b(construct|describe)\b',
    }
    return [name for name,pattern in patterns.items() if re.search(pattern,question,re.I)]


def _explicit_sort(question):
    m=re.search(r'\b(?:order(?:ed)?|sort(?:ed|ing)?)\s+(?:the\s+results\s+)?by\s+(.+)',question,re.I)
    if m:
        direction = 'DESC' if re.search(r'\b(desc|descending|highest\s+to\s+lowest)\b',m.group(1),re.I) else 'ASC'
        return (m.group(1).split()[0], direction)
    return None


def _explicit_limit(question):
    number_words={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10}
    word_match=re.search(r'\bup\s+to\s+('+'|'.join(number_words)+r')\b',question,re.I)
    if word_match:return number_words[word_match.group(1).lower()]
    patterns=[r'\bup\s+to\s+(\d+)\b',r'\blimited\s+to\s+(\d+)\b',
              r'\b(?:limit|return|show|top|first)\s+(\d+)\b',
              r'\b(?:return|show)\s+(?:the\s+)?first\s+(\d+)\b']
    for p in patterns:
        m=re.search(p,question,re.I)
        if m:return int(m.group(1))
    return None


def analyze_plan(answer, offered, question):
    d={'warnings':[],'errors':[],'derived_join_owner_id':None,
       'derived_branch_join':False,'explicit_filter_literals':[]}
    if not isinstance(answer,dict):return d
    lookup={c['id']:c for c in offered};paths=_paths(offered)
    unsupported=_unsupported_intent(question)
    d['unsupported_intent_signals']=unsupported
    if unsupported and answer.get('status')=='selected':
        d['errors'].append('Phase-2 operation requested: '+', '.join(unsupported))
    if answer.get('status')!='selected':return d
    selected=[x for x in (answer.get('projection_ids') or [])+(answer.get('existence_ids') or []) if x in paths]
    role_paths=[(paths[x][:-1] if lookup[x]['kind']=='property' else paths[x])
                for x in selected if paths[x]]
    owner,branch,topology=_deepest_owner(role_paths,offered)
    d.update(derived_join_owner_id=owner,derived_branch_join=branch,join_topology=topology)
    if branch and not owner:d['errors'].append('JOIN branches have no grounded meaningful owner')
    filters=[f for f in (answer.get('filters') or []) if isinstance(f,dict)]
    all_paths=[paths[x] for x in selected if paths[x]]
    all_paths += [paths[f['property_id']] for f in filters if f.get('property_id') in paths and paths[f['property_id']]]
    if len(all_paths)>1:
        common=list(all_paths[0])
        for p in all_paths[1:]:
            common=common[:next((i for i,(a,b) in enumerate(zip(common,p)) if a!=b),min(len(common),len(p)))]
        if len(common)<2:
            d['errors'].append('Selected paths share only domain root, not same entity')
    literals=_constraint_literals(question)
    d['explicit_filter_literals']=literals
    chosen={f.get('value','').casefold() for f in filters if isinstance(f.get('value'),str)}
    missing=[v for v in literals if v.casefold() not in chosen]
    if missing:d['errors'].append('Missing explicit filter values: '+', '.join(missing))
    if answer.get('count_target_id') is not None and not re.search(r'\b(count|how many|number of)\b',question,re.I):
        d['errors'].append('Unrequested COUNT')
    if answer.get('limit') is not None:
        requested=_explicit_limit(question)
        if requested!=answer['limit']:d['errors'].append('Unrequested or incorrect LIMIT')
    if answer.get('order_by'):
        if not re.search(r'\b(sort|sorted|order|ordered|ascending|descending|asc|desc)\b',question,re.I):
            d['errors'].append('Unrequested ORDER BY')
        else:
            qdir='DESC' if re.search(r'\b(desc|descending)\b',question,re.I) else 'ASC'
            if any(o.get('direction')!=qdir for o in answer['order_by'] if isinstance(o,dict)):
                d['errors'].append('ORDER BY direction disagrees with question')
    return d


def _tokens(value):
    """Conservative schema-name matching with plural normalization, not query templates."""
    words = re.findall(r'[A-Z]+(?=[A-Z][a-z]|\b)|[A-Z]?[a-z]+|[0-9]+', value)
    if not words:
        words = re.findall(r'[A-Za-z0-9]+', value)
    def singular(w):
        w = w.casefold()
        if len(w) > 4 and w.endswith('ies'):
            return w[:-3] + 'y'
        if len(w) > 5 and w.endswith(('sses', 'xes', 'ches', 'shes')):
            return w[:-2]
        if len(w) > 3 and w.endswith('s') and not w.endswith(('ss', 'us')):
            return w[:-1]
        return w
    normalized = [singular(w) for w in words]
    collapsed = []
    i = 0
    while i < len(normalized):
        if normalized[i:i+2] == ['end', 'point']:
            collapsed.append('endpoint')
            i += 2
        else:
            collapsed.append(normalized[i])
            i += 1
    return tuple(collapsed)


def _matches_schema_term(question, label):
    """Exact schema tokens; allow plural query for singular schema label only.

    In particular, 'connection points' must not match the schema concept
    'Connections' by reverse singularization of 'connection'.
    """
    def raw_tokens(value):
        return tuple(x.casefold() for x in re.findall(
            r'[A-Z]+(?=[A-Z][a-z]|\b)|[A-Z]?[a-z]+|[0-9]+', value))
    q = raw_tokens(question)
    l = raw_tokens(label)
    if not l:
        return False
    def equivalent(qword, lword):
        if qword == lword:
            return True
        if lword.endswith('s'):
            return False  # no reverse singularization of schema plurals
        return (qword == lword+'s' or
                (lword.endswith('y') and qword == lword[:-1]+'ies') or
                (qword == lword+'es' and lword.endswith(('s','x','ch','sh'))))
    return any(all(equivalent(q[i+j], word) for j,word in enumerate(l))
               for i in range(len(q)-len(l)+1))


def _explicit_filter_property_names(question):
    """Return property identifiers in simple Phase-1 comparison clauses."""
    names = []
    pattern = r'\b(?:where|and|or)\s+([A-Za-z_][\w]*)\s+(?:is|equals|equal\s+to|!=|>=|<=|=|>|<)\s+[^\s,;]+'
    for m in re.finditer(pattern, question, re.I):
        names.append(m.group(1))
    return names


def _requested_projection_concepts(question, index, shape_hits):
    """Only explicitly named concepts; no synonyms or implicit expansion."""
    return set(shape_hits)


def _schema_anchors(index, question):
    """Identify explicit shape/property references, including simple plurals."""
    from process_sim.dtwise.shacl_planner.grounding.subgraph import _short
    shape_hits = set()
    property_hits = {}
    for uri, shape in index.shapes.items():
        labels = [v for v in shape.get('labels', []) if 'shacl shape' not in v.casefold()]
        if any(_matches_schema_term(question, v) for v in labels):
            shape_hits.add(uri)
    for owner, props in index.properties.items():
        for prop in props:
            labels = [prop['name'], _short(prop['predicate']),
                      _short(prop['predicate']).removeprefix('has')]
            if any(_matches_schema_term(question, v) for v in labels):
                key = (owner, prop['predicate'], prop['property_shape'])
                property_hits[key] = prop
    return shape_hits, property_hits


def _verified_root_paths(index, targets, max_depth):
    """Enumerate bounded, cycle-free root-to-target paths using index edges only."""
    outgoing = defaultdict(list)
    incoming = set()
    for edge in index.edges:
        if edge['from'] in index.shapes and edge['to'] in index.shapes:
            outgoing[edge['from']].append(edge)
            incoming.add(edge['to'])
    for edges in outgoing.values():
        edges.sort(key=lambda e: (e['predicate'], e['to']))
    roots = sorted(set(index.shapes) - incoming)
    found = {}
    def walk(uri, nodes, edges):
        if uri in targets:
            found[(tuple(nodes), tuple((e['from'], e['predicate'], e['to'], e['property_shape'])
                                     for e in edges))] = (nodes[:], edges[:])
        if len(nodes) >= max_depth:
            return
        for edge in outgoing[uri]:
            if edge['to'] not in nodes:
                walk(edge['to'], nodes + [edge['to']], edges + [edge])
    for root in roots:
        walk(root, [root], [])
    return list(found.values())


def expand_verified_candidates(index, question, prepared, *, max_depth=6,
                               max_candidates=128):
    """Add explicit concept paths and properties, never inventing SHACL topology.

    Result-only paths are appended AFTER qualification because the existing
    qualify_candidates contract expects each prepared C path to end in a property.
    """
    from process_sim.dtwise.shacl_planner.grounding.subgraph import _short
    shape_hits, prop_hits = _schema_anchors(index, question)
    # The explicit anchor gate is intentionally conservative: no exact schema
    # vocabulary => don't let approximate embeddings fabricate domain support.
    anchor_evidence = {
        'explicit_shape_uris': sorted(shape_hits),
        'explicit_property_names': sorted({p['name'] for p in prop_hits.values()}),
        'schema_anchor_present': bool(shape_hits or prop_hits),
    }
    if not (shape_hits or prop_hits):
        return {'prompt': {'domain': index.domain, 'question': question,
                           'candidates': []}, 'registry': {}}, anchor_evidence, []

    # Relevant concept targets include explicitly named shapes and owners of
    # explicitly named properties. Semantic candidates remain untouched.
    targets = shape_hits | {p['owner'] for p in prop_hits.values()}
    root_paths = _verified_root_paths(index, targets, max_depth)
    registry = dict(prepared['registry'])
    prompt_candidates = list(prepared['prompt']['candidates'])
    seen = {(tuple(r['node_uris']), tuple((e['from'], e['predicate'], e['to'],
                e['property_shape']) for e in r['edges']),
             r['property']['owner'], r['property']['predicate'],
             r['property']['property_shape']) for r in registry.values()}
    counter = len(prompt_candidates)
    for nodes, edges in root_paths:
        owner = nodes[-1]
        for prop in index.properties.get(owner, []):
            key = (owner, prop['predicate'], prop['property_shape'])
            if key not in prop_hits:
                continue
            signature = (tuple(nodes), tuple((e['from'], e['predicate'], e['to'],
                e['property_shape']) for e in edges), *key)
            if signature in seen:
                continue
            if len(prompt_candidates) >= max_candidates:
                anchor_evidence['candidate_budget_reached'] = True
                break
            seen.add(signature)
            counter += 1
            cid = f'Cextra{counter}'
            names = [next((v for v in index.shapes[u].get('labels', [])
                           if 'shacl shape' not in v.casefold()), _short(u)) for u in nodes]
            prompt_candidates.append({'id': cid, 'path': ' → '.join([*names, prop['name']])})
            registry[cid] = {'node_uris': nodes[:], 'edges': edges[:], 'property': prop}
    augmented = {'prompt': {**prepared['prompt'], 'candidates': prompt_candidates},
                 'registry': registry}
    # Direct result paths are verified against index edges before exposing them.
    result_paths = []
    for nodes, edges in root_paths:
        for end in range(1, len(nodes) + 1):
            result_paths.append((nodes[:end], edges[:end-1]))
    return augmented, anchor_evidence, result_paths


def append_verified_result_paths(index, qualified, result_paths, *, max_candidates):
    """Append verified concept-level R paths, preserving all existing IDs."""
    from process_sim.dtwise.shacl_planner.grounding.subgraph import _short
    known = {tuple(r['node_uris']) for r in qualified['registry'].values()
             if r['kind'] == 'result'}
    counter = 0
    for nodes, edges in result_paths:
        key = tuple(nodes)
        if key in known:
            continue
        if len(qualified['prompt']['candidates']) >= max_candidates:
            break
        known.add(key)
        counter += 1
        cid = f'RX{counter}'
        labels = [next((v for v in index.shapes[u].get('labels', [])
                        if 'shacl shape' not in v.casefold()), _short(u)) for u in nodes]
        qualified['prompt']['candidates'].append({
            'id': cid, 'domain': index.domain, 'kind': 'result',
            'path': ' → '.join(labels),
        })
        qualified['registry'][cid] = {
            'domain': index.domain, 'kind': 'result', 'node_uris': nodes[:],
            'edges': edges[:], 'property': None, 'target_shape_uri': nodes[-1],
        }
    return qualified

def build_candidates(index, question, *, method, endpoint, embedding_model,
                     top_shapes, top_properties, max_candidates, max_depth):
    if method == 'exact':
        extracted = extract_question(index, question, connect=True)
        prepared = prepare_candidates(extracted, max_candidates=max_candidates)
        evidence = {
            'grounding': extracted.get('grounding'),
            'extracted_shapes': [n['name'] for n in extracted['nodes']],
            'extracted_properties': [p['name'] for p in extracted['properties']],
            'extraction_warnings': {k: extracted[k] for k in
                                    ('unresolved_connections', 'ambiguous_paths')
                                    if extracted.get(k)},
        }
    else:
        prepared = semantic_candidates(
            index, question, top_shapes=top_shapes, top_properties=top_properties,
            max_candidates=max_candidates, max_depth=max_depth,
            endpoint=endpoint, model=embedding_model,
        )
        evidence = {'retrieval': prepared.get('retrieval', {})}
    if method == 'expanded':
        prepared, anchors, result_paths = expand_verified_candidates(
            index, question, prepared, max_depth=max_depth,
            max_candidates=max_candidates,
        )
        evidence['schema_anchors'] = anchors
    else:
        result_paths = []
    qualified = qualify_candidates(index, prepared)
    if method == 'expanded':
        qualified = append_verified_result_paths(
            index, qualified, result_paths, max_candidates=max_candidates)
    return qualified, evidence



def requested_property_value_names(question, property_hits):
    """Detect explicit property-value retrieval, not arbitrary property mentions.

    Conservative language cues; property names come from SHACL, never from a
    query-specific vocabulary. Filters and mixed entity/property requests are
    left to the model and the remaining validators.
    """
    if re.search(r'\b(?:where|filter|ordered? by|sort(?:ed)? by)\b', question, re.I):
        return set()
    names = {p['name'].casefold() for p in property_hits.values()}
    if not names:
        return set()
    value_request = bool(re.search(r'\b(?:values?|its|their|belongs? to)\b', question, re.I))
    property_of = bool(re.search(r'\b(?:show|list|return|retrieve|get)\s+(?:the\s+)?[A-Za-z][A-Za-z0-9]*\s+(?:of|for)\b', question, re.I))
    possessive_request = bool(re.search(r"\b(?:retrieve|show|list|return|get)\b.*\b[A-Za-z][A-Za-z0-9]*['’]s\s+[A-Za-z][A-Za-z0-9]*\b", question, re.I))
    named_property_request = bool(
        re.search(r'\b(?:show|list|return|retrieve|get)\b.*\bproperty\b', question, re.I)
        or re.search(r'\b(?:show|list|return|retrieve|get)\b.*\busing\s+[A-Za-z][A-Za-z0-9]*\b', question, re.I)
        or re.search(r'^\s*(?:what|which)\s+[A-Za-z][A-Za-z0-9]*\s+(?:is|are)\s+(?:assigned|recorded|associated)\b', question, re.I)
    )
    if not (value_request or property_of or possessive_request or named_property_request):
        return set()
    return names


def focus_unambiguous_property_candidates(question, candidates, registry,
                                          shape_hits, property_hits):
    """Narrow a pure property-value request to its verified direct owner.

    Only focus when SHACL establishes exactly one direct property candidate
    under the explicitly matched concept shape(s). Several shape URIs may
    share the same user-facing label; do not require a single shape URI.
    Keep original candidate IDs for ambiguous/mixed requests. This scopes
    the prompt; it never fabricates an answer.
    """
    names = requested_property_value_names(question, property_hits)
    if len(names) != 1 or not shape_hits:
        return candidates, None
    name = next(iter(names))
    matches = [
        c for c in candidates
        if c['kind'] == 'property'
        and (c.get('property_name') or '').casefold() == name
        and (registry.get(c['id'], {}).get('node_uris') or [None])[-1] in shape_hits
    ]
    if len(matches) != 1:
        return candidates, None
    prop = matches[0]
    owner_nodes = registry[prop['id']]['node_uris']
    owner_results = [
        c for c in candidates
        if c['kind'] == 'result'
        and registry.get(c['id'], {}).get('node_uris') == owner_nodes
    ]
    focused = owner_results + matches
    return focused, {'property_name': name, 'property_candidate_id': prop['id'],
                     'owner_result_ids': [c['id'] for c in owner_results],
                     'original_candidate_count': len(candidates)}


def normalize_property_only_projections(answer, candidates, question):
    """Move redundant owner results to existence when only their properties are requested.

    This intentionally targets explicit `Show <Property> of ...` questions,
    not mixed entity/property requests. Candidate paths are verified upstream.
    """
    if answer.get('status') != 'selected':
        return answer
    m = re.search(r'^\s*(?:show|list|return|retrieve|get)\s+([A-Za-z][A-Za-z0-9]*)\s+of\b',
                  question, re.I)
    if not m:
        return answer
    property_name = m.group(1).casefold()
    lookup = {c['id']: c for c in candidates}
    projections = answer.get('projection_ids') or []
    property_ids = [cid for cid in projections if cid in lookup
                    and lookup[cid]['kind'] == 'property'
                    and (lookup[cid].get('property_name') or '').casefold() == property_name]
    if not property_ids:
        return answer
    property_paths = [_path_parts(lookup[cid]['path']) for cid in property_ids]
    kept = []
    moved = []
    for cid in projections:
        c = lookup.get(cid)
        if c and c['kind'] == 'result':
            result_path = _path_parts(c['path'])
            # Only the direct property owner; do not remove an explicitly
            # requested higher-level entity in a mixed projection query.
            if any(len(pp) == len(result_path) + 1 and pp[:-1] == result_path
                   for pp in property_paths):
                moved.append(cid)
                continue
        kept.append(cid)
    if not moved:
        return answer
    existence = list(answer.get('existence_ids') or [])
    for cid in moved:
        if cid not in existence:
            existence.append(cid)
    return {**answer, 'projection_ids': kept, 'existence_ids': existence}


def _path_parts(path):
    return tuple(part.strip() for part in path.split('→'))

def run_one(index, question, *, method='expanded', dry_run=False,
            model='qwen2.5-coder:7b', endpoint='http://127.0.0.1:11434',
            embedding_model='nomic-embed-text:latest', top_shapes=8,
            top_properties=8, max_candidates=128, max_depth=6):
    record={'question':question,'domain':index.domain,'model':model,'retrieval_method':method}
    # Phase-1 contract: at least one explicit SHACL concept label must appear.
    # Property-only anchors cannot establish a requested result concept.
    shape_hits, property_hits = _schema_anchors(index, question)
    record['exact_concept_matches'] = sorted(shape_hits)
    record['exact_property_names'] = sorted({p['name'] for p in property_hits.values()})
    if not shape_hits:
        record.update(status='no_explicit_concept', reason=(
            'No SHACL concept name explicitly present (case-insensitive/simple plural); '
            'do not infer synonyms. No Qwen call or embedding retrieval.'))
        return record
    # Do not let Qwen map a generic property (Status) to a longer schema field.
    requested_properties=_explicit_filter_property_names(question)
    exact_property_names={p['name'].casefold() for p in property_hits.values()}
    missing_properties=[name for name in requested_properties
                        if name.casefold() not in exact_property_names]
    if missing_properties:
        record.update(status='ambiguous_property',
                      ungrounded_filter_properties=missing_properties,
                      reason='Filter property lacks exact SHACL name; no Qwen call')
        return record
    unsupported=_unsupported_intent(question)
    if unsupported and not dry_run:
        record.update(status='unsupported_phase2',unsupported_operations=unsupported,
                      reason='Phase-2 feature detected before candidate retrieval; no Qwen call')
        return record
    try:
        qualified,evidence=build_candidates(index,question,method=method,endpoint=endpoint,
            embedding_model=embedding_model,top_shapes=top_shapes,
            top_properties=top_properties,max_candidates=max_candidates,max_depth=max_depth)
        all_candidates=qualified['prompt']['candidates']
        candidates, candidate_focus = focus_unambiguous_property_candidates(
            question, all_candidates, qualified['registry'], shape_hits, property_hits)
        topology_candidates=[{**c,'node_uris':qualified['registry'].get(c['id'],{}).get('node_uris',[])}
                             for c in candidates]
        prompt={**qualified['prompt'],'candidates':candidates}
        record.update({**evidence,'candidate_focus':candidate_focus,
            'candidate_count':len(candidates),
            'result_candidate_count':sum(c['kind']=='result' for c in candidates),
            'property_candidate_count':sum(c['kind']=='property' for c in candidates),
            'candidate_paths':candidates,'system_prompt':SYSTEM_PROMPT,'user_prompt':prompt})
        if dry_run:
            record['status']='dry_run'
            return record
        if method=='expanded' and not evidence['schema_anchors']['schema_anchor_present']:
            record['status']='no_schema_anchor'
            record['reason']='Conservative no-schema-anchor abstention; synonyms may be false negatives'
            return record
        if not candidates:
            record['status']='no_candidates'
            return record
        start=time.perf_counter()
        raw=ollama_select(prompt,model=model,endpoint=endpoint,system_prompt=SYSTEM_PROMPT)
        record['elapsed_seconds']=round(time.perf_counter()-start,3)
        record['raw_response']=raw
        try:
            answer=json.loads(raw)
        except json.JSONDecodeError as exc:
            record.update(status='invalid_json',validation_errors=[str(exc)])
            return record
        record['raw_answer']=answer
        answer=normalize_property_only_projections(answer,candidates,question)
        errors=validate_output(answer,candidates)
        diagnostics=analyze_plan(answer,topology_candidates,question)
        if answer.get('status')=='selected':
            # Python owns JOIN: Qwen's join bit is diagnostic only.
            answer={**answer, 'join':diagnostics['derived_branch_join'],
                    'join_owner_id':None}
            lookup={c['id']:c for c in topology_candidates}
            # Every result projection must end at an explicitly named concept;
            # ancestor concepts are allowed as traversal/existence context.
            for cid in answer.get('projection_ids',[]):
                c=lookup.get(cid)
                if c and c['kind']=='result':
                    nodes=c.get('node_uris') or []
                    if not nodes or nodes[-1] not in shape_hits:
                        diagnostics['errors'].append(
                            f'Projected result {cid} is not an explicitly named concept')
            # Every explicitly named concept must be represented by at least
            # one selected path (including its verified ancestors).
            selected_ids=(answer.get('projection_ids') or [])+(answer.get('existence_ids') or [])
            selected_ids += [f.get('property_id') for f in answer.get('filters',[])]
            selected_ids += [o.get('property_id') for o in answer.get('order_by',[])]
            if answer.get('count_target_id'):
                selected_ids.append(answer['count_target_id'])
            covered=set()
            for cid in selected_ids:
                covered.update(lookup.get(cid,{}).get('node_uris') or [])
            # A schema concept label can occur at several distinct shape URIs.
            # Require coverage of the named label, not every URI occurrence.
            # Parent context is enforced by verified selected SHACL paths.
            def labels_for(uri):
                shape = index.shapes.get(uri, {})
                return {v.casefold() for v in shape.get('labels', [])
                        if 'shacl shape' not in v.casefold()}
            covered_labels = set().union(*(labels_for(uri) for uri in covered)) if covered else set()
            required_labels = set()
            for uri in shape_hits:
                required_labels.update(labels_for(uri))
            for label in sorted(required_labels - covered_labels):
                diagnostics['errors'].append(
                    'Explicit concept not grounded in selected paths: ' + label)
            # Property-value retrieval must return property IDs directly owned
            # by an explicitly named concept, not every homonymous property
            # reachable through descendants or unrelated branches.
            value_names = requested_property_value_names(question, property_hits)
            if value_names:
                projected_properties = []
                for cid in answer.get('projection_ids', []):
                    c = lookup.get(cid)
                    if not c:
                        continue
                    if c['kind'] != 'property':
                        diagnostics['errors'].append(
                            f'Property-value request projects result {cid} instead of a property')
                        continue
                    projected_properties.append(c)
                    owner_nodes = c.get('node_uris') or []
                    if not owner_nodes or owner_nodes[-1] not in shape_hits:
                        diagnostics['errors'].append(
                            f'Projected property {cid} is not directly owned by a named concept')
                    if (c.get('property_name') or '').casefold() not in value_names:
                        diagnostics['errors'].append(
                            f'Projected property {cid} lacks explicit property-name evidence')
                if not projected_properties:
                    diagnostics['errors'].append('Property-value request has no property projection')
            # A chosen filter property must have the exact user-mentioned name.
            exact_names={p['name'].casefold() for p in property_hits.values()}
            for f in answer.get('filters',[]):
                c=lookup.get(f.get('property_id'))
                if c and (c.get('property_name') or '').casefold() not in exact_names:
                    diagnostics['errors'].append(
                        f'Filter {f.get("property_id")} lacks exact property-name evidence')
            requested_limit=_explicit_limit(question)
            if requested_limit is not None and answer.get('limit')!=requested_limit:
                diagnostics['errors'].append('Missing or incorrect requested LIMIT')
            if re.search(r'\b(count|how many|number of)\b',question,re.I) and not answer.get('count_target_id'):
                diagnostics['errors'].append('Missing requested COUNT')
            if _explicit_sort(question) and not answer.get('order_by'):
                diagnostics['errors'].append('Missing requested ORDER BY')
        elif answer.get('status')=='unsupported' and not _unsupported_intent(question):
            diagnostics['errors'].append('Unsupported response for Phase-1-only request')
        record['answer']=answer
        record['plan_diagnostics']=diagnostics
        errors.extend(diagnostics['errors'])
        record['validation_errors']=errors
        record['status']='valid_response' if not errors else 'invalid_response'
    except Exception as exc:
        record.update(status='error',error=f'{type(exc).__name__}: {exc}')
    return record


def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--schema',type=Path,required=True)
    ap.add_argument('--domain',default=None,help='Optional domain override; otherwise resolve from question')
    ap.add_argument('--questions',type=Path,help='JSON array of question strings')
    ap.add_argument('--mappings',type=Path,default=Path('semantic/ontology2/dtwise/cross-domain-mappings.json'),help='Approved cross-domain mapping registry')
    ap.add_argument('--model',default='qwen2.5-coder:7b')
    ap.add_argument('--endpoint',default='http://127.0.0.1:11434')
    ap.add_argument('--dry-run',action='store_true')
    ap.add_argument('--retrieval',choices=['exact','semantic','expanded','compare'],default='expanded')
    ap.add_argument('--embedding-model',default='nomic-embed-text:latest')
    ap.add_argument('--top-shapes',type=int,default=8)
    ap.add_argument('--top-properties',type=int,default=8)
    ap.add_argument('--max-candidates',type=int,default=128)
    ap.add_argument('--max-depth',type=int,default=6)
    ap.add_argument('--output',type=Path,default=Path('unified_shacl_results.json'))
    args=ap.parse_args()
    questions=json.loads(args.questions.read_text(encoding='utf-8')) if args.questions else DEFAULT_QUESTIONS
    if not isinstance(questions,list) or not questions or any(not isinstance(q,str) or not q.strip() for q in questions):
        ap.error('--questions must be a nonempty JSON array of nonempty strings')
    schema_data=json.loads(args.schema.read_text(encoding='utf-8'))
    available_domains=sorted({c['domain'] for c in schema_data.get('concepts', [])
                              if isinstance(c.get('domain'), str) and c['domain']})
    index_cache={}
    records=[]
    methods=['exact','semantic','expanded'] if args.retrieval=='compare' else [args.retrieval]
    for i,question in enumerate(questions,1):
        try:
            if args.domain is not None:
                domains=(resolve_domain(question,available_domains,
                                        override=args.domain,schema=schema_data),)
            else:
                domains=resolve_domains(question,available_domains,schema=schema_data)
            for domain in domains:
                if domain not in index_cache:
                    index_cache[domain]=load_index(args.schema,domain=domain)
            domain_error=None
        except DomainResolutionError as exc:
            domain_error=str(exc)
            domains=()
        for method in methods:
            if domain_error is not None:
                rec={'question':question,'retrieval_method':method,
                     'status':'domain_unresolved','reason':domain_error}
            elif len(domains)>1:
                from process_sim.dtwise.shacl_planner.cross_domain_phase1 import run_cross_domain
                rec=run_cross_domain({d:index_cache[d] for d in domains},question,
                    mapping_file=args.mappings,method=method,dry_run=args.dry_run,
                    model=args.model,endpoint=args.endpoint,embedding_model=args.embedding_model,
                    top_shapes=args.top_shapes,top_properties=args.top_properties,
                    max_candidates=args.max_candidates,max_depth=args.max_depth)
            else:
                rec=run_one(index_cache[domains[0]],question,method=method,dry_run=args.dry_run,
                    model=args.model,endpoint=args.endpoint,embedding_model=args.embedding_model,
                    top_shapes=args.top_shapes,top_properties=args.top_properties,
                    max_candidates=args.max_candidates,max_depth=args.max_depth)
            records.append(rec)
            print(f'\n[{i}/{len(questions)}] {method} {rec["status"]}: {question}',flush=True)
            print(f'  Candidates: {rec.get("candidate_count",0)} (R={rec.get("result_candidate_count",0)}, P={rec.get("property_candidate_count",0)})',flush=True)
            if 'prompt_candidate_count' in rec:
                print(f'  Qwen prompt: {rec["prompt_candidate_count"]} candidates, '
                      f'{rec["prompt_join_alternatives"]} JOIN alternatives, '
                      f'{rec["prompt_characters"]} characters',flush=True)
            for c in rec.get('candidate_paths',[]):
                print(f'    {c["id"]} [{c["kind"]}] {c["path"]}',flush=True)
            if 'answer' in rec:
                print('  Qwen:',json.dumps(rec['answer'],ensure_ascii=False),flush=True)
            if rec.get('plan_diagnostics'):
                d=rec['plan_diagnostics']
                print('  Topology: join=',d.get('derived_branch_join'),'owner=',d.get('derived_join_owner_id'),flush=True)
            if rec.get('validation_errors'):
                print('  Validation errors:',rec['validation_errors'],flush=True)
            if rec.get('error'):
                print('  Error:',rec['error'],flush=True)
    args.output.write_text(json.dumps(records,indent=2,ensure_ascii=False),encoding='utf-8')
    print(f'\nSaved {len(records)} records to {args.output.resolve()}')
    print('Summary:',json.dumps({s:sum(r['status']==s for r in records) for s in sorted({r['status'] for r in records})}))
    print('NOTE: valid_response does NOT prove semantic correctness or SPARQL executability.')
    print('NOTE: Phase-2 intent detection is conservative and can miss paraphrases.')
    print('NOTE: semantic/expanded retrieval makes Ollama embedding calls even in dry-run mode.')


if __name__=='__main__':
    main()
