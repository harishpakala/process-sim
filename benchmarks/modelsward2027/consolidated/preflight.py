"""Offline schema/routing preflight; no model or GraphDB calls."""
import json,re
from pathlib import Path
from process_sim.dtwise.shacl_planner.grounding.subgraph import load_index
from process_sim.dtwise.shacl_planner.multi_domain.domain_resolution import resolve_domains, DomainResolutionError
from process_sim.dtwise.shacl_planner.standalone_shacl_query_planner import _schema_anchors

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SCHEMA=ROOT/'semantic/ontology2/dtwise/dtwise-schema-index.json'
def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
    schema=load(SCHEMA)
    graphs=load(ROOT/'benchmarks/shacl_phase1/aast_instance_graphs.json')
    domains=sorted(graphs)
    indices={d:load_index(SCHEMA,domain=d) for d in domains}
    scenarios=load(HERE/'benchmark_queries_modelsward2027.json')['scenarios']
    passed=total=0
    for s in scenarios:
        if s['expected_behavior']=='reject': continue
        for p in s['paraphrases']:
            total+=1
            q=p['query']
            normalized=q
            for label,key in [('Asset Inventory','assetinventory'),('Product Catalog','productcatalog'),('OPC UA Connectivity','opcuaconnectivity'),('Engineering BOM','engineeringbom')]:
                normalized=re.sub(r'\b'+label+r'\b',key,normalized,flags=re.I)
            try:
                ds=resolve_domains(normalized,domains,schema=schema)
                if set(ds)!=set(s['expected_semantics']['domains']): raise ValueError('domain mismatch: '+str(ds))
                for d in ds:
                    shapes,props=_schema_anchors(indices[d],q)
                    if not shapes: raise ValueError('no explicit concept in '+d)
                    if s['scenario_id'].startswith('H'):
                        prop=s['expected_semantics']['projections'][0].split('.')[-1]
                        if prop.casefold() not in {v['name'].casefold() for v in props.values()}: raise ValueError('missing property '+prop)
                passed+=1
                if s['scenario_id'].startswith('H'): print(p['id'],'PASS',','.join(ds))
            except Exception as e: print(p['id'],'FAIL',str(e))
    print(f'Passed {passed}/{total} supported-query routing and anchor checks')
    return int(passed!=total)
if __name__=='__main__': raise SystemExit(main())
