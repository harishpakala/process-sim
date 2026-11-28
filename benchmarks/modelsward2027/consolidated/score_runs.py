"""Offline review queue and provisional contract-specific positional scoring."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

def evaluate(records, contracts):
    groups=defaultdict(list)
    seen=set()
    for r in records:
        method=r['configuration']['method']
        key=(method,r['model'],r['query_id'])
        if key in seen:
            raise ValueError(f'Duplicate evaluation: {key}')
        seen.add(key)
        contract=contracts[r['scenario_id']]
        mode=contract['mode']
        negative=mode=='negative'
        if negative != (r['expected_behavior']=='reject'):
            raise ValueError(f'Contract mismatch: {key}')
        status=r['status']
        field={'set':'positional_distinct_match','bag':'positional_multiset_match','ordered_pending':'positional_ordered_match'}.get(mode)
        agreement=None if negative else status=='executed' and r.get(field) is True
        outcome=('false_acceptance' if status=='negative_compiled_not_executed' else
                 'rejection_review_required' if status in ('planning_not_valid','domain_resolution_error') else
                 'decision_review_required') if negative else ('binding_match' if agreement else 'binding_failure')
        groups[(method,r['model'])].append(dict(query_id=r['query_id'],scenario_id=r['scenario_id'],
            mode=mode,status=status,negative=negative,positional_agreement=agreement,outcome=outcome,
            semantic_correctness=None,review_required=True,seconds=r['timings']['total']))
    output=[]
    for (method,model),rows in sorted(groups.items()):
        pos=[r for r in rows if not r['negative']]
        neg=[r for r in rows if r['negative']]
        scenarios=defaultdict(list)
        for r in pos: scenarios[r['scenario_id']].append(r)
        output.append(dict(method=method,model=model,attempts=len(rows),supported=len(pos),negative=len(neg),
            executed=sum(r['status']=='executed' for r in pos),
            positional_agreement=sum(r['positional_agreement'] for r in pos),
            negative_outcomes=dict(Counter(r['outcome'] for r in neg)),
            statuses=dict(Counter(r['status'] for r in rows)),
            complete_five_variant_scenarios=sum(len(v)==5 and all(r['positional_agreement'] for r in v) for v in scenarios.values()),
            median_seconds=median(r['seconds'] for r in rows),
            median_supported_seconds=median(r['seconds'] for r in pos) if pos else None,
            semantic_accuracy=None,review_queue=rows))
    return {'status':'provisional_positional_only','groups':output}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs',nargs='+',type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    contracts=json.loads(Path(__file__).with_name('result_contracts.json').read_text())['scenarios']
    records=[json.loads(line) for path in a.inputs for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    report=evaluate(records,contracts)
    with a.output.open('x',encoding='utf-8') as f: json.dump(report,f,indent=2)
if __name__=='__main__': main()
