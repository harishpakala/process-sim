"""Experiment 4: implicit-domain retrieval ablation and governed planning.

Domain selection uses only ranked schema hits (no question alias matching, gold
domain sets, catalog plans, or known domain count). A heuristic threshold selects
domains by rank-weighted evidence; results are exploratory, not validated intent.
Run from repository root with the existing Ollama schema embedding model.
"""
import argparse
import importlib.util
import json
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from semantic.dtwise_cross_domain import _validate_path
from semantic.dtwise_n_domain_planner import compile_n_domain

BASE = Path('experiments/vector_graph_rag')
GOLD = BASE / 'gold/dtwise_implicit_n_domain_16_review_draft.json'
INDEX = Path('semantic/ontology/dtwise/dtwise-schema-index.json')
CATALOG = Path('semantic/ontology/dtwise/cross-domain-mappings.json')
RECORDS = BASE / 'data/schema_records.jsonl'
VECTORS = BASE / 'data/schema_vectors.jsonl'
OUTPUT = BASE / 'data/implicit_domain_ablation_16.json'
METHODS = ('lexical', 'vector', 'hybrid')


def load_retriever():
    spec = importlib.util.spec_from_file_location(
        'dtwise_hybrid_retrieval', BASE / '06_evaluate_hybrid_retrieval.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def select_domains(hits, threshold=0.5, max_domains=4):
    """Rank-weighted domain coverage; threshold is relative to best domain.

    This is a deliberately simple baseline. Domain names and catalog contents
    never enter the selection decision.
    """
    if not 0 < threshold <= 1 or max_domains < 2:
        raise ValueError('Invalid domain selection parameters')
    scores = defaultdict(float)
    for rank, hit in enumerate(hits, 1):
        scores[hit['domain']] += 1.0 / (rank + 2)
    if not scores:
        return [], {}
    highest = max(scores.values())
    ordered = sorted(scores, key=lambda d: (-scores[d], d))
    # Select strongest max_domains first; sort alphabetically only for output.
    selected = sorted([d for d in ordered if scores[d] >= threshold * highest][:max_domains])
    return selected, dict(sorted(scores.items()))


def evaluate(benchmark, index, catalog, records, vectors, embed,
             top_k=10, weight=0.7, threshold=0.5, max_domains=4, limit=100):
    if top_k < 1 or not 0 <= weight <= 1:
        raise ValueError('Invalid retrieval parameters')
    known = {(c['domain'], c['uri']) for c in index.get('concepts', [])}
    retriever = load_retriever()
    rows = []
    for case in benchmark['cases']:
        question = case['question']
        ranked, _ = retriever.ranks(records, vectors, question, embed(question),
                                    top_k, weight)
        row = {'id': case['id'], 'source_case_id': case.get('source_case_id'),
               'question': question,
               'expected_domains_provisional': sorted(case['expected_domains']),
               'methods': {}}
        gold = set(case['expected_domains'])  # evaluation only
        for method in METHODS:
            hits = [{'domain': h['domain'], 'uri': h['uri']}
                    for h in ranked[method]
                    if (h['domain'], h['uri']) in known]
            selected, scores = select_domains(hits, threshold, max_domains)
            selected_set = set(selected)
            modes = {}
            for mode, allow_candidate in [('strict', False), ('exploratory', True)]:
                status, reason, sparql = 'abstained', None, None
                if len(selected) < 2:
                    reason = 'Fewer than two domains selected by retrieval'
                else:
                    try:
                        plan = compile_n_domain(question, index, catalog, selected_set,
                                                allow_candidate, limit, _validate_path)
                    except ValueError as exc:
                        reason = str(exc)
                    else:
                        status, sparql = 'ready', plan['sparql']
                expected = case['expected_' + mode + '_status']
                modes[mode] = {
                    'status': status, 'reason': reason, 'sparql': sparql,
                    'expected_status_provisional': expected,
                    'decision_match': status == expected,
                    'end_to_end_match': selected_set == gold and status == expected,
                    'executed': False,
                }
            row['methods'][method] = {
                'selected_domains': selected, 'domain_scores': scores,
                'retrieved_domains': sorted({h['domain'] for h in hits}),
                'hits': hits,
                'exact_domain_set_match': selected_set == gold,
                'domain_precision': len(selected_set & gold) / len(selected_set) if selected_set else 0.0,
                'domain_recall': len(selected_set & gold) / len(gold),
                'modes': modes,
            }
        rows.append(row)
    summary = {'total_cases': len(rows), 'methods': {}}
    for method in METHODS:
        rr = [r['methods'][method] for r in rows]
        summary['methods'][method] = {
            'exact_domain_set_matches': sum(x['exact_domain_set_match'] for x in rr),
            'mean_domain_precision': sum(x['domain_precision'] for x in rr) / len(rr),
            'mean_domain_recall': sum(x['domain_recall'] for x in rr) / len(rr),
            'strict': {
                'decision_matches': sum(x['modes']['strict']['decision_match'] for x in rr),
                'end_to_end_matches': sum(x['modes']['strict']['end_to_end_match'] for x in rr),
                'ready': sum(x['modes']['strict']['status'] == 'ready' for x in rr),
            },
            'exploratory': {
                'decision_matches': sum(x['modes']['exploratory']['decision_match'] for x in rr),
                'end_to_end_matches': sum(x['modes']['exploratory']['end_to_end_match'] for x in rr),
                'ready': sum(x['modes']['exploratory']['status'] == 'ready' for x in rr),
                'abstention_reasons': dict(sorted(Counter(
                    x['modes']['exploratory']['reason'] for x in rr
                    if x['modes']['exploratory']['reason']).items())),
            },
        }
    return {
        'evaluation_type': 'implicit_domain_retrieval_ablation',
        'benchmark_status': benchmark.get('status'),
        'top_k': top_k, 'vector_weight': weight,
        'selection_threshold': threshold, 'max_selected_domains': max_domains,
        'limitations': [
            'Heuristic rank-weighted domain selection; not a validated semantic intent model.',
            'Provisional paraphrases and labels require independent expert review.',
            'Decision accuracy can be inflated by abstention-heavy strict mode.',
            'Candidate SPARQL is not executed and does not imply verified identity.',
            'Hyperparameters must be fixed before evaluation on an independent test set.',
        ],
        'summary': summary, 'results': rows,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--benchmark', type=Path, default=GOLD)
    ap.add_argument('--index', type=Path, default=INDEX)
    ap.add_argument('--catalog', type=Path, default=CATALOG)
    ap.add_argument('--records', type=Path, default=RECORDS)
    ap.add_argument('--vectors', type=Path, default=VECTORS)
    ap.add_argument('--output', type=Path, default=OUTPUT)
    ap.add_argument('--endpoint', default='http://localhost:11434')
    ap.add_argument('--top-k', type=int, default=10)
    ap.add_argument('--vector-weight', type=float, default=0.7)
    ap.add_argument('--selection-threshold', type=float, default=0.5)
    ap.add_argument('--max-domains', type=int, default=4)
    ap.add_argument('--limit', type=int, default=100)
    args = ap.parse_args()
    retriever = load_retriever()
    records = retriever.load_jsonl(args.records)
    vectors_list = retriever.load_jsonl(args.vectors)
    vectors = {v['id']: v for v in vectors_list}
    if len(vectors) != len(records) or any(r['id'] not in vectors for r in records):
        raise ValueError('Vectors do not match schema records')
    models = {v['model'] for v in vectors_list}
    if len(models) != 1:
        raise ValueError('Expected one embedding model')
    model = models.pop()

    def embed(q):
        request = urllib.request.Request(
            args.endpoint.rstrip('/') + '/api/embed',
            json.dumps({'model': model, 'input': q}).encode('utf-8'),
            {'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)['embeddings'][0]

    report = evaluate(
        json.loads(args.benchmark.read_text(encoding='utf-8')),
        json.loads(args.index.read_text(encoding='utf-8')),
        json.loads(args.catalog.read_text(encoding='utf-8')),
        records, vectors, embed, args.top_k, args.vector_weight,
        args.selection_threshold, args.max_domains, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n',
                           encoding='utf-8')
    print(json.dumps(report['summary'], indent=2))
    print('Wrote:', args.output)


if __name__ == '__main__':
    main()
