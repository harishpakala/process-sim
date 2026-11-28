"""Schema-informed direct SPARQL baseline; no candidate selection or compiler."""
import json
from process_sim.dtwise.experimental_shacl_ollama import ollama_select

SYSTEM = """Generate a read-only SPARQL SELECT directly from the question and supplied schema.
Use only explicit concept names, verified schema paths and registered cross-domain mapping keys.
Do not infer missing domains, owners, properties or substitute a different join key.
Return JSON with exactly status, sparql, reason. Status is selected, ambiguous, unresolved or unsupported.
For selected return a SELECT query; otherwise sparql must be null. No external SERVICE or dataset clauses.
Support entity and property retrieval, simple comparisons, AND/OR, ORDER BY and LIMIT.
Preserve duplicate values unless distinctness is explicitly requested. Use named graphs from the registry.
Reject unsupported requests rather than silently dropping constraints."""

def direct_plan(question,schema,mappings,graphs,*,model,endpoint,transport=None):
    # Full schema context, independent of expected domain or reference answer.
    prompt={'question':question,'schema':schema,'registered_mappings':mappings,'instance_graphs':graphs}
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
