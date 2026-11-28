"""Reproduce paired pilot positional metrics; no semantic correctness claims."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import median

def analyze(paths):
    runs={}
    common=None
    expected=None
    for method,path in zip(('direct','ablated','full'),paths):
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        assert len(rows)==45
        cfg=rows[0]['configuration']
        assert cfg['method']==method and all(r['configuration']==cfg for r in rows)
        shared={k:v for k,v in cfg.items() if k not in ('method','direct_module_sha256')}
        if common is None: common=shared
        assert shared==common
        keys={(r['query_id'],r['model'],r['question'],r['expected_behavior']) for r in rows}
        assert len(keys)==45
        if expected is None: expected=keys
        assert keys==expected
        runs[method]=rows
    contracts=json.loads(Path(__file__).with_name('result_contracts.json').read_text())['scenarios']
    def agrees(r):
        mode=contracts[r['scenario_id']]['mode']
        key={'set':'positional_distinct_match','bag':'positional_multiset_match','ordered_pending':'positional_ordered_match'}[mode]
        return r['status']=='executed' and r.get(key) is True
    result={}
    for (method,rows),path in zip(runs.items(),paths):
        pos=[r for r in rows if r['expected_behavior']!='reject']
        neg=[r for r in rows if r['expected_behavior']=='reject']
        assert len(pos)==40 and len(neg)==5
        result[method]={'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'supported':len(pos),'executed':sum(r['status']=='executed' for r in pos),'positional_agreement':sum(agrees(r) for r in pos),'negative_statuses':dict(Counter(r['status'] for r in neg)),'mapping_rejections':sum(r.get('planner_record',{}).get('status')=='no_approved_cross_domain_mapping' for r in neg),'median_all_seconds':median(r['timings']['total'] for r in rows),'median_supported_seconds':median(r['timings']['total'] for r in pos),'supported_failures':[r['query_id'] for r in pos if not agrees(r)]}
    return {'status':'pilot_positional_only','configuration':common,'methods':result}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs',nargs=3,type=Path,help='Direct, ablated, full JSONL files in that order')
    a=p.parse_args()
    print(json.dumps(analyze(a.inputs),indent=2))
