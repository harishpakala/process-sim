"""Score independent lexical/vector/hybrid retrieval reports against benchmark V1.

Input JSON: {"results":[{"id":"Q01", "lexical":{"hits":[{"domain":"dexpi","uri":"..."}]},
"vector":{"hits":[...]}, "hybrid":{"hits":[...]}, "predicted_historical":false}, ...]}.
No oracle-domain filtering, query execution, or fabricated concept labels.
"""
import argparse, json
from pathlib import Path

MODES=('lexical','vector','hybrid')
def score(gold, pred):
    gold,pred=set(gold),set(pred)
    tp=len(gold & pred)
    precision=tp/len(pred) if pred else 0
    recall=tp/len(gold) if gold else 0
    return {'exact':gold==pred,'precision':precision,'recall':recall,
            'f1':2*precision*recall/(precision+recall) if precision+recall else 0}

def evaluate(benchmark,report,index=None):
    cases=benchmark['cases']; outputs={}; indexed=None
    if index is not None:
        indexed={(c.get('domain'),c.get('uri')) for c in index.get('concepts',[])}
    by_id={r['id']:r for r in report.get('results',[])}
    if len(by_id)!=len(report.get('results',[])):
        raise ValueError('Duplicate retrieval result IDs')
    for mode in MODES:
        rows=[]
        for c in cases:
            r=by_id.get(c['id'])
            if r is None or mode not in r:
                rows.append({'id':c['id'],'status':'missing'});continue
            hits=r[mode].get('hits',[])
            if not isinstance(hits,list):raise ValueError('hits must be a list')
            domains=list(dict.fromkeys(h['domain'] for h in hits if h.get('domain')))
            predicted=domains[:len(c['expected_domains'])] # oracle cardinality: diagnostic only
            selected=r[mode].get('selected_domains')
            actual=score(c['expected_domains'],selected) if selected is not None else None
            top3=set(domains[:3]); recall3=len(set(c['expected_domains']) & top3)/len(c['expected_domains'])
            gold={(g['domain'],g['uri']) for g in c.get('gold_concepts',[]) if 'domain' in g and 'uri' in g}
            concepts=[(h.get('domain'),h.get('uri')) for h in hits[:10]]
            concept_recall=len(gold & set(concepts))/len(gold) if gold else None
            rows.append({'id':c['id'],'status':'scored','selected_domains':selected,
                         'ranked_domains':domains,'oracle_cardinality_top_domains_diagnostic':predicted,
                         'domain_metrics':actual,'domain_recall_at_3':recall3,
                         'concept_recall_at_10':concept_recall,
                         'indexed_top10_count':sum(x in indexed for x in concepts) if indexed is not None else None})
        valid=[x for x in rows if x['status']=='scored']; dm=[x['domain_metrics'] for x in valid if x['domain_metrics'] is not None]
        cr=[x['concept_recall_at_10'] for x in valid if x['concept_recall_at_10'] is not None]
        outputs[mode]={'summary':{'evaluated':len(valid),'missing':len(rows)-len(valid),
           'exact_domain_set_accuracy':sum(x['exact'] for x in dm)/len(dm) if dm else None,
           'macro_domain_f1':sum(x['f1'] for x in dm)/len(dm) if dm else None,
           'mean_domain_recall_at_3':sum(x['domain_recall_at_3'] for x in valid)/len(valid) if valid else None,
           'mean_concept_recall_at_10':sum(cr)/len(cr) if cr else None,
           'concept_labeled_cases':len(cr)},'cases':rows}
    temporal=[(c['historical'],by_id[c['id']]['predicted_historical']) for c in cases
              if c['id'] in by_id and 'predicted_historical' in by_id[c['id']]]
    return {'benchmark_status':benchmark['status'],'results':outputs,
            'temporal_intent':{'evaluated':len(temporal),'accuracy':sum(a==b for a,b in temporal)/len(temporal) if temporal else None},
            'limitations':['Exact-set accuracy requires independently predicted selected_domains; absent predictions yield null.',
                           'Concept recall remains null until reviewed gold concept URIs are supplied.',
                           'Recall@3 is candidate coverage, not final domain selection.',
                           'No mappings, temporal observations, or SPARQL queries are executed.']}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--benchmark',type=Path,default=Path('experiments/vector_graph_rag/data/benchmark_15.json'))
    ap.add_argument('--retrieval',type=Path,required=True);ap.add_argument('--index',type=Path)
    ap.add_argument('--output',type=Path,default=Path('experiments/vector_graph_rag/data/hybrid_domain_concept_eval_15.json'))
    a=ap.parse_args(); b=json.loads(a.benchmark.read_text());r=json.loads(a.retrieval.read_text());i=json.loads(a.index.read_text()) if a.index else None
    result=evaluate(b,r,i);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v['summary'] for k,v in result['results'].items()},indent=2));print('Wrote:',a.output)
if __name__=='__main__':main()
