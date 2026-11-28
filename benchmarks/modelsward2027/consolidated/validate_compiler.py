"""Oracle path compiler check against live reference bindings; not an LLM evaluation."""
import argparse,json
from collections import Counter
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from process_sim.dtwise.shacl_planner.grounding.subgraph import load_index
from process_sim.dtwise.shacl_planner.sparql_compiler import compile_single_domain
HERE=Path(__file__).resolve().parent
SCHEMA=HERE.parents[2]/'semantic/ontology2/dtwise/dtwise-schema-index.json'
def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def execute(url,q):
    req=Request(url,data=urlencode({'query':q,'infer':'false'}).encode(),headers={'Accept':'application/sparql-results+json','Content-Type':'application/x-www-form-urlencoded'})
    with urlopen(req,timeout=60) as f: r=json.load(f)
    cols=r['head']['vars']
    if len(cols)!=1: raise ValueError('Expected one projection')
    return Counter(json.dumps(b[cols[0]],sort_keys=True) for b in r['results']['bindings'])
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graphdb-url',required=True)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if a.output.exists(): p.error('Output exists')
    schema=load(SCHEMA)
    refs={r['scenario_id']:r for r in load(HERE/'reference_queries_modelsward2027.json')['references']}
    results=[]
    for s in load(HERE/'benchmark_queries_modelsward2027.json')['scenarios']:
        sid=s['scenario_id']
        if not sid.startswith('H'): continue
        sem=s['expected_semantics']; d=sem['domains'][0]
        parts=sem['projections'][0].split('.')
        ns='https://example.org/'+d+'/'
        ix=load_index(SCHEMA,domain=d)
        r={'scenario_id':sid,'status':'fail'}
        try:
            classes={}
            for rel in schema['relationships']:
                if rel.get('domain')==d and rel['predicate'] in ('http://www.w3.org/ns/shacl#class','http://www.w3.org/ns/shacl#targetClass'):
                    classes.setdefault(rel['subject'],set()).add(rel['object'])
            matches=[]
            def walk(nodes,edges):
                if len(nodes)>6: return
                # Child class constraints belong to incoming property shapes, not NodeShapes.
                tail=edges[-(len(parts)-1):]
                if len(tail)==len(parts)-1 and all(ns+c in classes.get(e['property_shape'],set()) for c,e in zip(parts[:-1],tail)):
                    for prop in ix.properties.get(nodes[-1],[]):
                        if prop['predicate']==ns+'has'+parts[-1]:
                            matches.append((nodes,edges,prop))
                for e in ix.edges:
                    if e['from']==nodes[-1] and e['to'] not in nodes: walk(nodes+[e['to']],edges+[e])
            roots={rel['subject'] for rel in schema['relationships'] if rel.get('domain')==d and rel['predicate']=='http://www.w3.org/ns/shacl#targetClass'}
            for root in sorted(roots & set(ix.shapes)): walk([root],[])
            if len(matches)!=1: raise ValueError('Expected unique rooted owner path; found '+str(len(matches)))
            nodes,edges,prop=matches[0]
            record={'status':'valid_response','validation_errors':[],'domain':d,'candidate_paths':[{'id':'P1','kind':'property'}],'candidate_registry':{'P1':{'domain':d,'kind':'property','node_uris':nodes,'edges':edges,'property':prop}},'answer':{'status':'selected','projection_ids':['P1'],'existence_ids':[],'filters':[],'boolean_operator':'NONE','join':False,'join_owner_id':None,'count_target_id':None,'order_by':[],'limit':None}}
            q=compile_single_domain(record,ix,schema)
            reference=refs[sid]['sparql']
            expected=execute(a.graphdb_url,reference)
            actual=execute(a.graphdb_url,q)
            r.update(sparql=q,reference_sparql=reference,owner_path=nodes,predicates=[e['predicate'] for e in edges]+[prop['predicate']],actual_rows=sum(actual.values()),reference_rows=sum(expected.values()),binding_match=actual==expected,status='pass' if actual==expected and expected else 'fail')
        except Exception as e: r['error']=str(e)
        results.append(r)
        print(sid,r['status'],r.get('actual_rows',r.get('error','')))
    passed=sum(r['status']=='pass' for r in results)
    with a.output.open('x',encoding='utf-8') as f: json.dump({'oracle_selected':True,'inference_requested':False,'results':results,'passed':passed,'total':len(results)},f,indent=2)
    print(f'Passed {passed}/{len(results)} oracle compiler checks')
    return int(passed!=len(results))
if __name__=='__main__': raise SystemExit(main())
