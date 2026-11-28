"""Offline descriptive audit of a complete historical benchmark JSONL."""
import argparse
import json
import statistics
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent

def analyze(records, manifest, model):
    expected = {p['id']: (s, p) for s in manifest['scenarios'] for p in s['paraphrases']}
    rows = [r for r in records if r['model'] == model]
    counts = Counter(r['query_id'] for r in rows)
    if set(counts) != set(expected) or any(n != 1 for n in counts.values()):
        raise ValueError('Incomplete, unexpected or duplicate query IDs')
    if any(r['configuration'] != rows[0]['configuration'] for r in rows):
        raise ValueError('Mixed configurations')
    if not rows[0]['configuration']['full']:
        raise ValueError('Full run required')
    for r in rows:
        s, p = expected[r['query_id']]
        if (r['scenario_id'], r['question'], r['expected_behavior']) != (s['scenario_id'], p['query'], s['expected_behavior']):
            raise ValueError('Manifest mismatch: ' + r['query_id'])
    supported = [r for r in rows if r['expected_behavior'] != 'reject']
    negative = [r for r in rows if r['expected_behavior'] == 'reject' and r['scenario_id'] != 'N44']
    def match(r):
        s, _ = expected[r['query_id']]
        key = 'positional_ordered_match' if s['expected_semantics'].get('order_by') else 'positional_multiset_match'
        return r['status'] == 'executed' and r.get(key) is True
    def detail(r):
        p = r.get('planner_record', {})
        return {k:r.get(k) for k in ('query_id','status','error','sparql','expected_rejection')} | {'planner_status':p.get('status'),'validation_errors':p.get('validation_errors')}
    def latency(rs):
        values = sorted(r['timings']['total'] for r in rs)
        return {'median_seconds':statistics.median(values), 'p95_seconds':values[max(0, __import__('math').ceil(.95*len(values))-1)]}
    groups = {r['scenario_id'] for r in supported}
    return {'model':model,'total':len(rows),'supported':len(supported),
            'executed':sum(r['status']=='executed' for r in supported),
            'positional_agreement':sum(map(match,supported)),
            'all_variants_agree_scenarios':sum(all(match(r) for r in supported if r['scenario_id']==s) for s in groups),
            'supported_scenarios':len(groups),'supported_statuses':dict(Counter(r['status'] for r in supported)),
            'supported_failures':[detail(r) for r in supported if not match(r)],
            'supported_latency':latency(supported),
            'negative_in_scope':len(negative),'negative_statuses':dict(Counter(r['status'] for r in negative)),
            'negative_compiled':[detail(r) for r in negative if r['status']=='negative_compiled_not_executed'],
            'negative_details':[detail(r) for r in negative],
            'excluded_N44':sum(r['scenario_id']=='N44' for r in rows),
            'configuration':rows[0]['configuration'],
            'note':'Provisional positional comparison; structural and rejection-reason review required. N44 excluded only from negative summary.'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    records=[json.loads(line) for line in a.input.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    manifest=json.loads((HERE/'benchmark_queries_modelsward2027.json').read_text(encoding='utf-8-sig'))
    report=[analyze(records,manifest,m) for m in sorted({r['model'] for r in records})]
    if not report: raise ValueError('Empty input')
    with a.output.open('x',encoding='utf-8') as f: json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
