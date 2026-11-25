"""ModelsWard smoke test: same ten questions for each model; no gold-domain routing."""
import argparse
import json
import sys
import time
from pathlib import Path
from collections import Counter


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--benchmark', type=Path, default=Path('benchmarks/modelsward2027/benchmark_queries_modelsward2027.json'))
    p.add_argument('--models', nargs='+', default=['qwen2.5-coder:7b', 'llama3.1:8b', 'mistral:7b'])
    p.add_argument('--endpoint', default='http://127.0.0.1:11434')
    p.add_argument('--retrieval', choices=['exact','semantic','expanded'], default='expanded')
    p.add_argument('--output-dir', type=Path, default=Path('benchmark_results/modelsward_smoke'))
    p.add_argument('--schema', type=Path, default=Path('semantic/ontology2/dtwise/dtwise-schema-index.json'))
    p.add_argument('--mappings', type=Path, default=Path('semantic/ontology2/dtwise/cross-domain-mappings.json'))
    p.add_argument('--graphs', type=Path, default=Path('benchmarks/shacl_phase1/aast_instance_graphs.json'))
    p.add_argument('--limit', type=int, default=10)
    a = p.parse_args()
    data = json.loads(a.benchmark.read_text(encoding='utf-8-sig'))
    # Round-robin scenario families, one paraphrase per scenario first.
    groups = {}
    for s in data['scenarios']:
        groups.setdefault(s['type'], []).append(s)
    ordered = []
    while any(groups.values()):
        for group in groups.values():
            if group: ordered.append(group.pop(0))
    questions = [(s,v) for i in range(max(len(s['paraphrases']) for s in ordered)) for s in ordered for v in s['paraphrases'][i:i+1]]
    if not 1 <= a.limit <= len(questions): p.error('Invalid question limit')
    questions = questions[:a.limit]
    sys.path.insert(0, str(Path('src').resolve()))
    from process_sim.dtwise.shacl_planner.grounding.subgraph import load_index
    from process_sim.dtwise.shacl_planner.multi_domain.domain_resolution import resolve_domains
    from process_sim.dtwise.shacl_planner.standalone_shacl_query_planner import run_one
    from process_sim.dtwise.shacl_planner.cross_domain_phase1 import run_cross_domain
    from process_sim.dtwise.shacl_planner.sparql_compiler import compile_single_domain
    from process_sim.dtwise.shacl_planner.cross_domain_sparql_compiler import compile_cross_domain
    def load(path): return json.loads(path.read_text(encoding='utf-8-sig'))
    schema, mappings, graphs = map(load, (a.schema,a.mappings,a.graphs))
    domains = ['dexpi','ecad','assetinventory','productcatalog','opcuaconnectivity']
    indices = {d:load_index(a.schema, domain=d) for d in domains}
    a.output_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    import re
    for model in a.models:
        name = re.sub(r'[^a-zA-Z0-9_.-]', '_', model)
        rows = []
        with (a.output_dir / (name+'.jsonl')).open('w', encoding='utf-8') as f:
            for s,v in questions:
                q = v['query']; start = time.perf_counter()
                r = {'id':v['id'],'query':q,'model':model,'expected_behavior':s.get('expected_behavior')}
                stage = 'routing'
                try:
                    normalized = q
                    for label,key in [('Asset Inventory','assetinventory'),('Product Catalog','productcatalog'),('OPC UA Connectivity','opcuaconnectivity')]:
                        normalized = re.sub(r'\b'+label+r'\b',key,normalized,flags=re.I)
                    ds = list(resolve_domains(normalized,domains,schema=schema)); r['domains']=ds
                    ix = {d:indices[d] for d in ds}
                    stage = 'planning'
                    opts = dict(method=a.retrieval,model=model,endpoint=a.endpoint)
                    if not ds: raise ValueError('No resolved domains')
                    record = run_one(ix[ds[0]],q,**opts) if len(ds)==1 else run_cross_domain(ix,q,mapping_file=a.mappings,**opts)
                    r['record']=record
                    if record.get('status')!='valid_response' or record.get('validation_errors'):
                        r['status']='planning_not_valid'
                    else:
                        stage='compilation'
                        r['sparql']=compile_single_domain(record,ix[ds[0]],schema) if len(ds)==1 else compile_cross_domain(record,ix,schema,graphs,mappings)
                        r['status']='compiled'
                except Exception as e:
                    r.update(status=stage+'_error',error=f'{type(e).__name__}: {e}')
                r['seconds']=round(time.perf_counter()-start,3)
                rows.append(r); f.write(json.dumps(r,default=str,ensure_ascii=False)+'\n'); f.flush()
                print(model,v['id'],r['status'],r['seconds'],flush=True)
        summary.append({'model':model,'questions':len(rows),'statuses':dict(Counter(r['status'] for r in rows)),'seconds':sum(r['seconds'] for r in rows)})
    (a.output_dir/'model_comparison.json').write_text(json.dumps({'question_ids':[v['id'] for s,v in questions],'retrieval':a.retrieval,'models':summary,'note':'Smoke diagnostics only; no GraphDB execution or semantic correctness labels.'},indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
