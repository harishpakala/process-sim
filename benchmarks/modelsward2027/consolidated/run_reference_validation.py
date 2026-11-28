"""Execute independently authored candidate references; never invoke the planner."""
import argparse,json,os,time,hashlib
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlencode
from datetime import datetime,timezone

def main():
    p=argparse.ArgumentParser();p.add_argument('--graphdb-url',default=os.getenv('GRAPHDB_SPARQL_ENDPOINT'));p.add_argument('--timeout',type=int,default=60);p.add_argument('--all',action='store_true',help='Validate all supported references');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists(): p.error('Output already exists')
    endpoint=a.graphdb_url or input('GraphDB repository SPARQL URL: ').strip()
    root=Path(__file__).resolve().parent; source=root/'reference_queries_modelsward2027.json'; data=json.loads(source.read_text(encoding='utf-8')); results=[]
    for ref in data['references']:
        if not a.all and not ref['scenario_id'].startswith('H'): continue
        q=ref['sparql']; t=time.perf_counter(); r={'scenario_id':ref['scenario_id'],'reference_query_id':ref['reference_query_id']}
        try:
            if not q.startswith('SELECT '): raise ValueError('Only authored SELECT references allowed')
            req=Request(endpoint,data=urlencode({'query':q,'infer':'false'}).encode(),headers={'Accept':'application/sparql-results+json','Content-Type':'application/x-www-form-urlencoded'})
            with urlopen(req,timeout=a.timeout) as response: payload=json.load(response)
            rows=payload['results']['bindings']; cols=payload['head']['vars']; assert isinstance(rows,list) and isinstance(cols,list)
            r.update(status='pass' if (not rows)==ref['expected_empty'] else 'unexpected_cardinality',row_count=len(rows),variables=cols,bindings=rows,distinct_rows=len({json.dumps(row,sort_keys=True) for row in rows}))
        except Exception as e:r.update(status='error',error=str(e))
        r['elapsed_seconds']=time.perf_counter()-t;results.append(r);print(r['scenario_id'],r['status'],r.get('row_count',''))
    report={'scope':'all' if a.all else 'new_only','endpoint':endpoint,'created_at_utc':datetime.now(timezone.utc).isoformat(),'reference_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'inference_requested':False,'results':results,'passed':sum(r['status']=='pass' for r in results),'total':len(results),'note':'Pass checks execution and expected emptiness only; review full RDF bindings, ordering ties and semantics before freeze.'}
    with a.output.open('x',encoding='utf-8') as f: json.dump(report,f,indent=2)
    print(f"Passed {report['passed']}/{report['total']}");return 0 if report['passed']==report['total'] else 1
if __name__=='__main__':raise SystemExit(main())
