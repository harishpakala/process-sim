"""Evaluate deterministic hybrid schema retrieval against provisional concept labels.

No instance relationships or cross-domain joins are inferred. Requires existing Ollama vectors.
"""
import argparse
import json
import math
import re
import urllib.request
from pathlib import Path

def load_jsonl(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]

def tokens(s):
    return set(re.findall(r'[a-z0-9]+', re.sub(r'([a-z0-9])([A-Z])', r'\\1 \\2', s).lower()))

def cosine(a, b):
    if len(a) != len(b):
        raise ValueError('Embedding dimension mismatch')
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b))/(na*nb) if na and nb else 0.0

def ranks(records, vectors, query, qv, k, vector_weight=0.7):
    qtokens = tokens(query)
    candidates = []
    for r in records:
        if r['kind'] not in ('class', 'property'):
            continue
        vt = cosine(qv, vectors[r['id']]['embedding'])
        local = re.split(r'[/#]', r['uri'])[-1]
        name_overlap = len(qtokens & tokens(local)) / max(1, len(qtokens))
        text_overlap = len(qtokens & tokens(r['text'])) / max(1, len(qtokens))
        lexical = 0.65*name_overlap + 0.35*text_overlap
        candidates.append((r, vt, lexical))
    # Rank fusion avoids incompatible raw cosine and lexical score scales.
    vr = sorted(candidates, key=lambda x: (-x[1], x[0]['id']))
    lr = sorted(candidates, key=lambda x: (-x[2], x[0]['id']))
    vpos = {r['id']: i for i, (r, _, _) in enumerate(vr, 1)}
    lpos = {r['id']: i for i, (r, _, _) in enumerate(lr, 1)}
    hybrid = sorted(candidates, key=lambda x: (-(vector_weight/(60+vpos[x[0]['id']])+(1-vector_weight)/(60+lpos[x[0]['id']])), x[0]['id']))
    return {'vector': [x[0] for x in vr[:k]], 'lexical': [x[0] for x in lr if x[2]>0][:k], 'hybrid': [x[0] for x in hybrid[:k]]}

def metrics(hits, gold):
    positions = [i for i,r in enumerate(hits,1) if (r['domain'],r['uri']) in gold]
    return {'recall_at_5': sum(p<=5 for p in positions)/len(gold),
            'recall_at_10': sum(p<=10 for p in positions)/len(gold),
            'precision_at_10': sum(p<=10 for p in positions)/10,
            'reciprocal_rank': 1/min(positions) if positions else 0.0}

def evaluate(records, vectors, questions, embed, k=10, weight=0.7):
    known = {(r['domain'],r['uri']) for r in records if r['kind'] in ('class','property')}
    rows = []
    for item in questions:
        q = item['question']
        gold = {(g['domain'],g['uri']) for g in item.get('gold_concepts',[])}
        missing = sorted(gold-known)
        if not gold:
            raise ValueError(f'No gold concepts for question: {q}')
        if missing:
            print('WARNING: gold concepts absent from schema records:', q, missing)
        ranked = ranks(records,vectors,q,embed(q),k,weight)
        row = {'question':q,'gold_concepts':item['gold_concepts'],
               'missing_gold_in_records':[{'domain':d,'uri':u} for d,u in missing]}
        for method,hits in ranked.items():
            row[method] = {'metrics':metrics(hits,gold),
                           'hits':[{'domain':r['domain'],'uri':r['uri'],'kind':r['kind'],'id':r['id']} for r in hits]}
        rows.append(row)
    summary = {}
    for method in ('vector','lexical','hybrid'):
        summary[method] = {key:sum(r[method]['metrics'][key] for r in rows)/len(rows)
                           for key in ('recall_at_5','recall_at_10','precision_at_10','reciprocal_rank')}
    return {'note':'Provisional annotations; domain review required. No relationship or join verification.', 'top_k':k,
            'summary_macro':summary,'results':rows}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--records',type=Path,default=Path('experiments/vector_graph_rag/data/schema_records.jsonl'))
    ap.add_argument('--vectors',type=Path,default=Path('experiments/vector_graph_rag/data/schema_vectors.jsonl'))
    ap.add_argument('--gold',type=Path,default=Path('experiments/vector_graph_rag/gold/dtwise_gold_existing_3_review_draft.json'))
    ap.add_argument('--output',type=Path,default=Path('experiments/vector_graph_rag/data/hybrid_evaluation.json'))
    ap.add_argument('--endpoint',default='http://localhost:11434')
    ap.add_argument('--top-k',type=int,default=10)
    ap.add_argument('--vector-weight',type=float,default=0.7)
    args=ap.parse_args()
    if args.top_k<10: ap.error('--top-k must be at least 10 for Recall@10')
    if not 0<=args.vector_weight<=1: ap.error('--vector-weight must be between 0 and 1')
    records=load_jsonl(args.records)
    vectors={v['id']:v for v in load_jsonl(args.vectors)}
    if len(vectors)!=len(records) or any(r['id'] not in vectors for r in records):
        raise ValueError('Vectors do not match records; rebuild embeddings')
    models={v['model'] for v in vectors.values()}
    if len(models)!=1: raise ValueError('Mixed embedding models')
    model=models.pop()
    questions=json.loads(args.gold.read_text(encoding='utf-8'))
    def embed(q):
        req=urllib.request.Request(args.endpoint.rstrip('/')+'/api/embed',
            json.dumps({'model':model,'input':q}).encode(),{'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=120) as response:
            return json.load(response)['embeddings'][0]
    result=evaluate(records,vectors,questions,embed,args.top_k,args.vector_weight)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(result['summary_macro'],indent=2))
    print('Wrote:',args.output)

if __name__=='__main__':
    main()
