"""Evaluate retrieval/expansion with explicit, expert-reviewed gold concept IRIs.

Gold labels are optional; missing labels produce null metrics, never fabricated zeros.
Domain precision/recall are weak diagnostics, not proof of grounded joins.
"""
import argparse
import json
from pathlib import Path


def prf(gold, found):
    if not gold:
        return {'precision': None, 'recall': None, 'f1': None}
    p = len(gold & found) / len(found) if found else 0.0
    r = len(gold & found) / len(gold)
    return {'precision': p, 'recall': r, 'f1': 2*p*r/(p+r) if p+r else 0.0}


def evaluate(retrieval, gold=None, expanded=None):
    labels = {x['question']: x for x in (gold or [])}
    contexts = {x['question']: x for x in expanded.get('results', [])} if expanded else {}
    rows = []
    for item in retrieval['results']:
        q = item['question']
        label = labels.get(q, {})
        domains = set(label.get('expected_domains', item.get('expected_domains', [])))
        # Gold concept URIs must be supplied by an expert. Domain is part of
        # identity to prevent conflating identical IRIs in different catalogs.
        gold_concepts = {(x['domain'], x['uri']) for x in label.get('gold_concepts', [])}
        row = {'question': q, 'gold_concepts_provided': bool(gold_concepts)}
        for method in ('vector', 'lexical'):
            hits = item[method]['hits']
            found_domains = {h['domain'] for h in hits}
            found_concepts = {(h['domain'], h['uri']) for h in hits}
            first_rank = next((i for i, h in enumerate(hits, 1) if (h['domain'], h['uri']) in gold_concepts), None)
            row[method] = {
                'domain': prf(domains, found_domains),
                'concept': prf(gold_concepts, found_concepts),
                'first_gold_concept_rank': first_rank,
                'reciprocal_rank': (1.0 / first_rank) if first_rank else (0.0 if gold_concepts else None),
            }
        if q in contexts:
            context = contexts[q]
            expanded_concepts = {(x['domain'], x['uri']) for x in context.get('reached_concepts', [])}
            row['expanded'] = {
                'domain': prf(domains, {d for d, _ in expanded_concepts}),
                'concept': prf(gold_concepts, expanded_concepts),
                'schema_edge_count': len(context.get('schema_edges', [])),
                'shape_path_count': len(context.get('shape_paths', [])),
                'join_verified': False,
            }
        rows.append(row)
    return {'evaluation_note': 'Gold concept metrics require independently reviewed gold_concepts; domain labels alone are insufficient.', 'results': rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--retrieval', type=Path, default=Path('experiments/vector_graph_rag/data/retrieval_results.json'))
    ap.add_argument('--expanded', type=Path, default=Path('experiments/vector_graph_rag/data/expanded_context.json'))
    ap.add_argument('--gold', type=Path, help='Optional expert-reviewed JSON list of {question, expected_domains, gold_concepts:[{domain,uri}]}')
    ap.add_argument('--output', type=Path, default=Path('experiments/vector_graph_rag/data/grounding_evaluation.json'))
    args = ap.parse_args()
    retrieval = json.loads(args.retrieval.read_text(encoding='utf-8'))
    gold = json.loads(args.gold.read_text(encoding='utf-8')) if args.gold else None
    expanded = json.loads(args.expanded.read_text(encoding='utf-8')) if args.expanded.exists() else None
    report = evaluate(retrieval, gold, expanded)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    for row in report['results']:
        print(row['question'])
        for method in ('vector', 'lexical'):
            print(f"  {method}: domain={row[method]['domain']} concept={row[method]['concept']}")
    print('Wrote:', args.output)


if __name__ == '__main__':
    main()
