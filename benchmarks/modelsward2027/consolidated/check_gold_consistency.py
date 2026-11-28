"""Compare fresh reference results with frozen gold and full ordered references."""
import argparse,json,re,sys
from pathlib import Path
from collections import Counter
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from ordered_semantics import compare_ordered
from result_semantics import term

def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gold',type=Path,required=True)
    p.add_argument('--current',type=Path,required=True)
    a=p.parse_args()
    gold,current=load(a.gold),load(a.current)
    refs={r['scenario_id']:r for r in load(HERE/'reference_queries_modelsward2027.json')['references']}
    ordered=load(HERE/'consolidated_ordered_references.json')
    for report in (gold,current):
        if report['scope']!='all' or report['inference_requested'] is not False or len(report['results'])!=50 or any(r['status']!='pass' for r in report['results']) or set(r['scenario_id'] for r in report['results'])!=set(refs):
            raise ValueError('Incomplete reference report')
    for key in ('endpoint','reference_sha256'):
        if gold[key]!=current[key]: raise ValueError('Report mismatch: '+key)
    old={r['scenario_id']:r for r in gold['results']}
    failures=[]
    for r in current['results']:
        sid=r['scenario_id']; e=old[sid]; ref=refs[sid]; cols=e['variables']
        def tuples(x): return [tuple(term(row.get(v)) for v in cols) for row in x['bindings']]
        ok=set(cols)==set(r['variables']) and Counter(tuples(r))==Counter(tuples(e))
        if ref['ordered']:
            limit=int(re.search(r'LIMIT (\d+)$',ref['sparql']).group(1))
            roles=ref['projection_roles']; alignment=dict(zip(roles,cols))
            actual={'head':{'vars':r['variables']},'results':{'bindings':r['bindings']}}
            ok=ok and tuples(r)==tuples(e) and compare_ordered(actual,ordered[sid],roles,alignment,alignment,limit,'ORDER BY DESC' in ref['sparql'])['contract_match']
        print(sid,'PASS' if ok else 'FAIL')
        if not ok: failures.append(sid)
    print('Passed',50-len(failures),'/ 50; ordered scenarios checked:',len(ordered))
    return int(bool(failures))
if __name__=='__main__': raise SystemExit(main())
