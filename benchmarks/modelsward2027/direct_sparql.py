"""Schema-informed direct SPARQL baseline; no candidate selection or compiler."""
import json
from process_sim.dtwise.experimental_shacl_ollama import ollama_select

SYSTEM = """Generate a read-only SPARQL SELECT directly from the question and supplied schema.
Use only explicit concept names, verified schema paths and registered cross-domain mapping keys.
Do not infer missing domains, owners, properties or substitute a different join key.
Return JSON with exactly status, sparql, reason. Status is selected, ambiguous, unresolved or unsupported.
For selected return a SELECT query; otherwise sparql must be null. No external SERVICE or dataset clauses.
Support entity and property retrieval, simple comparisons, AND/OR, ORDER BY and LIMIT.
Preserve duplicate values unless distinctness is explicitly requested. Use named graphs from the registry. Expand or declare supplied namespace prefixes. Schema triples list owner class, predicate, and target class or value. If explicit_domains is empty, abstain as ambiguous.
Reject unsupported requests rather than silently dropping constraints."""

import re

def compact_context(question,schema,mappings,graphs):
    aliases={'assetinventory':r'asset\s*inventory','productcatalog':r'product\s*catalog','opcuaconnectivity':r'opc\s*ua\s*connectivity','engineeringbom':r'engineering\s*bom','ecad':'ecad','dexpi':'dexpi'}
    domains=[d for d in sorted(graphs) if re.search(r'\b'+aliases[d]+r'\b',question,re.I)]
    active=domains or sorted(graphs)
    prefixes={d:'https://example.org/'+d+'/' for d in active}
    prefixes['aas']='https://example.org/aas/'
    def short(uri):
        for k,v in prefixes.items():
            if uri.startswith(v): return k+':'+uri[len(v):]
        return '<'+uri+'>'
    rel=[r for r in schema['relationships'] if r['domain'] in active]
    types={}
    children={}
    for r in rel:
        if r['predicate']=='http://www.w3.org/ns/shacl#targetClass':
            types.setdefault(r['subject'],set()).add(r['object'])
        if r['predicate']=='http://www.w3.org/ns/shacl#class':
            types.setdefault(r['subject'],set()).add(r['object'])
        if r['predicate']=='http://www.w3.org/ns/shacl#node':
            children.setdefault(r['subject'],set()).add(r['object'])
    for prop,nodes in children.items():
        for node in nodes: types.setdefault(node,set()).update(types.get(prop,set()))
    triples=set()
    for p in schema['shape_paths']:
        if p['domain'] not in active: continue
        owners=types.get(p['node_shape'],set())
        targets=types.get(p['property_shape'],set())
        for owner in owners:
            triples.add((short(owner),short(p['path']),', '.join(sorted(short(t) for t in targets)) or 'value'))
    classes=sorted({short(c['uri']) for c in schema['concepts'] if c['domain'] in active and c['kind']=='class'})
    keys=[{k:(short(m[k]) if k.endswith('_property') else m[k]) for k in ('id','left_domain','right_domain','left_property','right_property')} for m in mappings if m.get('verified') and {m['left_domain'],m['right_domain']}<=set(active)]
    return {'question':question,'explicit_domains':domains,'available_domains':sorted(graphs),'prefixes':prefixes,'classes':classes,'schema_triples':sorted(triples),'registered_mappings':keys,'instance_graphs':{d:graphs[d] for d in active}}

def direct_plan(question,schema,mappings,graphs,*,model,endpoint,transport=None):
    # Domain selection uses question text only; no reference metadata.
    prompt=compact_context(question,schema,mappings,graphs)
    timing={}
    raw=ollama_select(prompt,model=model,endpoint=endpoint,transport=transport,system_prompt=SYSTEM,timing=timing)
    record={'raw_response':raw,'prompt':prompt,'system_prompt':SYSTEM,'timing':timing}
    try:
        answer=json.loads(raw)
        if not isinstance(answer,dict) or set(answer)!={'status','sparql','reason'} or not isinstance(answer['reason'],str) or not answer['reason'].strip():
            raise ValueError('Invalid response contract')
        status=answer['status']
        if status not in ('selected','ambiguous','unresolved','unsupported'): raise ValueError('Invalid status')
        if status=='selected':
            if not isinstance(answer['sparql'],str) or not answer['sparql'].strip(): raise ValueError('Missing SPARQL')
        elif answer['sparql'] is not None: raise ValueError('Rejected response contains SPARQL')
        record.update(answer=answer,status='valid_response' if status=='selected' else 'model_abstained')
    except (ValueError,TypeError) as e: record.update(status='invalid_response',error=str(e))
    return record

def check_select(query):
    # Parse the entire query, not just a leading SELECT token.
    from rdflib.plugins.sparql.parser import parseQuery
    from rdflib.plugins.sparql.parserutils import CompValue
    parsed=parseQuery(query)
    if parsed[1].name!='SelectQuery': raise ValueError('Only SELECT permitted')
    def walk(x):
        from pyparsing import ParseResults
        if isinstance(x,CompValue):
            if x.name in ('ServiceGraphPattern','DatasetClause'): raise ValueError('External service or dataset clause forbidden')
            for v in x.values(): walk(v)
        elif isinstance(x,(list,tuple,ParseResults)):
            for v in x: walk(v)
    walk(parsed)
    return query

def supply_prefixes(query,prefixes):
    """Supply only known missing namespace declarations; preserve model query body."""
    declared={m.group(1) for m in re.finditer(r'\bPREFIX\s+([\w-]+):\s*<[^>]+>',query,re.I)}
    return '\n'.join([f'PREFIX {k}: <{v}>' for k,v in sorted(prefixes.items()) if k not in declared]+[query])
