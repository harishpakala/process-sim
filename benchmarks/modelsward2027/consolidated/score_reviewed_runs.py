"""Batch semantic scoring with explicit review evidence; no model or database calls."""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from semantic_review import evaluate

def key(r):
    return (r['method'],r['model'],r['query_id'])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('inputs',nargs='+',type=Path)
    p.add_argument('--gold',required=True,type=Path)
    p.add_argument('--reviews',type=Path)
    p.add_argument('--ordered-references',type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    gold=json.loads(a.gold.read_text(encoding='utf-8-sig'))
    if gold['scope']!='all' or gold['inference_requested'] is not False:
        raise ValueError('Full inference-disabled reference report required')
    refs={r['scenario_id']:{'head':{'vars':r['variables']},'results':{'bindings':r['bindings']}} for r in gold['results'] if r['status']=='pass'}
    if len(refs)!=50:
        raise ValueError('Expected 50 successful reference scenarios')
    contracts=json.loads(Path(__file__).with_name('result_contracts.json').read_text())['scenarios']
    reviews={}
    for r in json.loads(a.reviews.read_text(encoding='utf-8-sig')) if a.reviews else []:
        k=key(r)
        if k in reviews: raise ValueError(f'Duplicate review: {k}')
        reviews[k]=r
    ordered=json.loads(a.ordered_references.read_text(encoding='utf-8-sig')) if a.ordered_references else {}
    digest=hashlib.sha256(a.gold.read_bytes()).hexdigest()
    seen=set()
    groups=defaultdict(list)
    for path in a.inputs:
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip(): continue
            r=json.loads(line)
            cfg=r['configuration']
            if cfg['hashes']['consolidated_reference_full.json']!=digest:
                raise ValueError('Reference fingerprint mismatch')
            k=(cfg['method'],r['model'],r['query_id'])
            if k in seen: raise ValueError(f'Duplicate run: {k}')
            seen.add(k)
            sid=r['scenario_id']
            review=reviews.get(k)
            if review and review.get('record_sha256')!=hashlib.sha256(line.encode('utf-8')).hexdigest():
                raise ValueError(f'Review does not match raw record: {k}')
            result=evaluate(r,contracts[sid],review,refs.get(sid),ordered.get(sid))
            groups[k[:2]].append(dict(query_id=k[2],scenario_id=sid,negative=contracts[sid]['mode']=='negative',**result))
    if set(reviews)-seen: raise ValueError('Review contains unknown run IDs')
    out=[]
    for (method,model),rows in sorted(groups.items()):
        pos=[r for r in rows if not r['negative']]
        neg=[r for r in rows if r['negative']]
        pending=sum(r.get('semantic_correctness') is None for r in pos)
        correct=sum(r.get('semantic_correctness') is True for r in pos)
        out.append(dict(method=method,model=model,supported=len(pos),negative=len(neg),semantic_correct=correct,
            supported_pending=pending,semantic_accuracy=correct/len(pos) if pos and not pending else None,
            negative_outcomes=dict(Counter(r['outcome'] for r in neg)),records=rows))
    with a.output.open('x',encoding='utf-8') as f:
        json.dump({'status':'review_based_partial_or_complete','gold_sha256':digest,'groups':out},f,indent=2)
if __name__=='__main__': main()
