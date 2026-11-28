"""ModelsWard smoke and full benchmark runner. No final correctness labels; review plans and projections."""
import argparse, json, time, hashlib, sys, re
from pathlib import Path
from collections import Counter
from urllib.request import Request, urlopen
from urllib.parse import urlencode

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SCHEMA=ROOT/'semantic/ontology2/dtwise/dtwise-schema-index.json'
MAPPINGS=SCHEMA.with_name('cross-domain-mappings.json')
GRAPHS=ROOT/'benchmarks/shacl_phase1/aast_instance_graphs.json'
def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(bindings, cols):
    return [tuple(json.dumps(b.get(c),sort_keys=True,ensure_ascii=False) for c in cols) for b in bindings]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--graphdb-url',help='Optional GraphDB SELECT endpoint; omit for compile-only smoke test')
    p.add_argument('--ollama-url',default='http://127.0.0.1:11434')
    p.add_argument('--models',nargs='+',default=['qwen2.5-coder:7b','llama3.1:8b','mistral:7b'])
    p.add_argument('--output',default='smoke_results_v2.jsonl')
    p.add_argument('--limit',type=int,default=10,choices=range(1,11))
    p.add_argument('--full',action='store_true',help='Evaluate every paraphrase in the manifest')
    p.add_argument('--resume',action='store_true',help='Resume an existing output with identical configuration')
    p.add_argument('--scenarios', nargs='+', help='Evaluate all paraphrases of selected scenario IDs')
    p.add_argument('--consolidated',action='store_true',help='Use the six-domain consolidated manifest')
    p.add_argument('--gold',type=Path,help='Full consolidated reference validation report')
    p.add_argument('--dry-run',action='store_true',help='Validate inputs and enumerate jobs without model or database calls')
    p.add_argument('--method',choices=['direct','full'],default='full')
    a=p.parse_args()
    if a.method=='direct' and not a.consolidated: p.error('Direct baseline requires --consolidated')
    if a.consolidated and not a.gold: p.error('--consolidated requires --gold')
    if a.gold and not a.consolidated: p.error('--gold requires --consolidated')
    if a.scenarios and a.full: p.error('--scenarios and --full are mutually exclusive')
    if a.scenarios and not a.graphdb_url and not a.dry_run: p.error('--scenarios requires --graphdb-url')
    if a.scenarios and len(set(a.scenarios)) != len(a.scenarios): p.error('Duplicate scenario IDs')
    if a.full and not a.graphdb_url and not a.dry_run: p.error('--full requires --graphdb-url')
    if len(set(a.models)) != len(a.models): p.error('Duplicate models')
    from process_sim.dtwise.shacl_planner.grounding.subgraph import load_index
    from process_sim.dtwise.shacl_planner.multi_domain.domain_resolution import resolve_domains
    from process_sim.dtwise.shacl_planner.standalone_shacl_query_planner import run_one
    from process_sim.dtwise.shacl_planner.cross_domain_phase1 import run_cross_domain
    from process_sim.dtwise.shacl_planner.sparql_compiler import compile_single_domain
    from process_sim.dtwise.shacl_planner.cross_domain_sparql_compiler import compile_cross_domain
    schema=load(SCHEMA); mappings=load(MAPPINGS); graphs=load(GRAPHS)
    folder=HERE/'consolidated' if a.consolidated else HERE
    bp=folder/'benchmark_queries_modelsward2027.json'; rp=folder/'reference_queries_modelsward2027.json'
    gp=a.gold.resolve() if a.consolidated else HERE/'reference_validation_results.json'
    gold=load(gp)
    if gold['reference_sha256']!=digest(rp): raise ValueError('Reference hash mismatch')
    refs={r['scenario_id']:r for r in gold['results']}
    scenarios={s['scenario_id']:s for s in load(bp)['scenarios']}
    if a.consolidated:
        expected={sid for sid,s in scenarios.items() if s['expected_behavior']!='reject'}
        if gold.get('scope')!='all' or gold.get('inference_requested') is not False or set(refs)!=expected or len(gold['results'])!=len(expected) or any(r.get('status')!='pass' for r in refs.values()):
            raise ValueError('Full successful consolidated reference report required')
        if a.graphdb_url and gold.get('endpoint')!=a.graphdb_url: raise ValueError('Reference endpoint mismatch')
    domains=sorted(graphs) if a.consolidated else ['dexpi','ecad','assetinventory','productcatalog','opcuaconnectivity']
    indices={d:load_index(SCHEMA,domain=d) for d in domains}
    output=HERE/a.output
    smoke=['SD01','CD01','N39','E45','SD02','CD02','N40','E46','SD03','CD03']
    if a.scenarios and set(a.scenarios)-set(scenarios): p.error('Unknown scenario IDs: '+str(sorted(set(a.scenarios)-set(scenarios))))
    selected=a.scenarios or (list(scenarios) if a.full else smoke[:a.limit])
    jobs=[(sid,p) for sid in selected for p in (scenarios[sid]['paraphrases'] if a.full or a.scenarios else scenarios[sid]['paraphrases'][:1])]
    hashes={x.name:digest(x) for x in [bp,rp,SCHEMA,MAPPINGS,GRAPHS,gp]}
    config=dict(full=a.full,limit=None if a.full else a.limit,models=a.models,graphdb_url=a.graphdb_url,ollama_url=a.ollama_url,retrieval='expanded',hashes=hashes)
    if a.consolidated: config['benchmark']='consolidated'; config['runner_sha256']=digest(Path(__file__))
    if a.consolidated: config['method']=a.method
    if a.scenarios: config['scenarios']=a.scenarios
    if a.dry_run:
        print('Domains:', ', '.join(domains))
        print('Scenarios:',len(selected),'Queries:',len(jobs),'Evaluations:',len(jobs)*len(a.models))
        print('Dry run: no model or GraphDB calls')
        return
    completed=set()
    if a.resume:
     with output.open(encoding='utf-8') as previous:
      for line in previous:
       old=json.loads(line)
       if old.get('configuration')!=config: raise ValueError('Resume configuration mismatch')
       key=(old['query_id'],old['model'])
       if key in completed: raise ValueError('Duplicate checkpoint: '+str(key))
       completed.add(key)
    print('Evaluations:',len(jobs)*len(a.models),'completed:',len(completed),flush=True)
    with output.open('a' if a.resume else 'x',encoding='utf-8') as f:
      for model in a.models:
       for sid,paraphrase in jobs:
        s=scenarios[sid]; q=paraphrase['query']; qid=paraphrase['id']
        if (qid,model) in completed: continue
        r=dict(scenario_id=sid,query_id=qid,configuration=config,question=q,model=model,expected_behavior=s['expected_behavior'],timings={},status='started',final_correctness='manual_review_required',hashes={x.name:digest(x) for x in [bp,rp,SCHEMA,MAPPINGS,GRAPHS]})
        start=time.perf_counter(); stage='domain_resolution'; t=start
        def mark(): r['timings'][stage]=time.perf_counter()-t
        try:
         if a.method=='direct':
          from direct_sparql import direct_plan,check_select
          stage='planning'; t=time.perf_counter()
          record=direct_plan(q,schema,mappings,graphs,model=model,endpoint=a.ollama_url)
          mark(); r['planner_record']=record
          if record['status']!='valid_response':
           r['status']=record['status']; continue
          stage='query_policy'; t=time.perf_counter()
          r['sparql']=record['answer']['sparql']
          sparql=check_select(r['sparql']); mark()
         else:
          # Fixed display-name normalization; no scenario metadata used for routing.
          normalized=q
          for label,key in [('Asset Inventory','assetinventory'),('Product Catalog','productcatalog'),('OPC UA Connectivity','opcuaconnectivity'),('Engineering BOM','engineeringbom')]:
           normalized=re.sub(r'\b'+label+r'\b',key,normalized,flags=re.I)
          ds=resolve_domains(normalized,domains,schema=schema); mark()
          r['resolved_domains']=list(ds)
          expected_domains=s.get('expected_semantics',{}).get('domains')
          r['domain_match']=None if expected_domains is None else set(ds)==set(expected_domains)
          r['expected_rejection']=s.get('expected_semantics',{}).get('expected_rejection')
          ix={d:indices[d] for d in ds}; stage='planning'; t=time.perf_counter()
          opts=dict(method='expanded',model=model,endpoint=a.ollama_url)
          record=run_one(ix[ds[0]],q,**opts) if len(ds)==1 else run_cross_domain(ix,q,mapping_file=MAPPINGS,**opts)
          mark(); r['planner_record']=record
          if record.get('status')!='valid_response' or record.get('validation_errors'):
           r['status']='planning_not_valid'
           if s['expected_behavior']=='reject': r['negative_outcome']='rejection_reason_review_required'
           continue
          stage='compilation'; t=time.perf_counter()
          sparql=compile_single_domain(record,ix[ds[0]],schema) if len(ds)==1 else compile_cross_domain(record,ix,schema,graphs,mappings)
          mark(); r['sparql']=sparql
         if not sparql.lstrip().upper().startswith('SELECT'): raise ValueError('Only SELECT allowed')
         if s['expected_behavior']=='reject':
          r['status']='negative_compiled_not_executed'; r['negative_outcome']='accepted_plan_review_required'; continue
         if not a.graphdb_url:
          r['status']='compiled'; continue
         stage='execution'; t=time.perf_counter()
         req=Request(a.graphdb_url,data=urlencode({'query':sparql,'infer':'false'}).encode(),headers={'Accept':'application/sparql-results+json','Content-Type':'application/x-www-form-urlencoded'})
         with urlopen(req,timeout=60) as response: result=json.load(response)
         mark(); r['result']=result; r['status']='executed'; stage='comparison'; t=time.perf_counter()
         ref=refs[sid]; cols=result['head']['vars']; bindings=result['results']['bindings']; r['row_count']=len(bindings)
         r['reference_row_count']=ref['row_count']; r['projection_alignment']='positional_only_unverified'
         if len(cols)==len(ref['variables']):
          actual=rows(bindings,cols); expected=rows(ref['bindings'],ref['variables'])
          r['positional_multiset_match']=Counter(actual)==Counter(expected)
          r['positional_distinct_match']=set(actual)==set(expected)
          r['positional_ordered_match']=actual==expected
          if not bindings and not ref['bindings']:
           r['empty_result_semantics']='manual_plan_review_required'
         else: r['projection_alignment']='arity_mismatch'
         mark()
        except Exception as e:
         mark(); r['status']=stage+'_error'; r['error']=f'{type(e).__name__}: {e}'
        finally:
         r['timings']['total']=time.perf_counter()-start
         r['runner_version']='5.0-consolidated' if a.consolidated else '4.0-full'
         r['expected_semantics']=s.get('expected_semantics',{})
         r['hashes']['reference_validation_results.json']=digest(gp)
         f.write(json.dumps(r,default=str,ensure_ascii=False)+'\n'); f.flush()
         print(qid,model,r['status'],round(r['timings']['total'],3),flush=True)
    print('Saved',output)
if __name__=='__main__': main()
