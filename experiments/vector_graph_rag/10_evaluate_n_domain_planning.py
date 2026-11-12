"""Audit the 33 provisional retrieval questions against governed N-domain planning.

This is a planning *feasibility and safety audit*, not an independently
reviewed end-to-end accuracy benchmark. Single-domain questions are recorded
as out of scope for the N-domain planner rather than marked as failures.
Run from repo root: python -m experiments.vector_graph_rag.10_evaluate_n_domain_planning
"""
import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path

from semantic.dtwise_n_domain_planner import _normalize
from semantic.dtwise_cross_domain import _validate_path
from semantic.dtwise_n_domain_planner import compile_n_domain

BASE = Path('experiments/vector_graph_rag')
GOLD = BASE / 'gold/dtwise_gold_concepts_review_draft.json'
RETRIEVAL = BASE / 'data/hybrid_evaluation_33_v3.json'
INDEX = Path('semantic/ontology/dtwise/dtwise-schema-index.json')
CATALOG = Path('semantic/ontology/dtwise/cross-domain-mappings.json')


def evaluate(gold, retrieval, index, catalog, method='hybrid',
             allow_candidate=False, limit=100):
    if method not in ('hybrid', 'vector', 'lexical'):
        raise ValueError('Unsupported retrieval method')
    if not isinstance(gold, list):
        raise ValueError('Gold questions must be a list')
    rows_by_question = {}
    for row in retrieval.get('results', []):
        rows_by_question.setdefault(row.get('question'), []).append(row)
    indexed = {(c['domain'], c['uri']) for c in index.get('concepts', [])}
    plans = _normalize(catalog)
    rows = []
    for i, item in enumerate(gold, 1):
        question = item['question']
        domains = item.get('expected_domains', [])
        if not isinstance(domains, list) or not domains or len(domains) != len(set(domains)):
            raise ValueError('Missing or duplicate provisional domains for question ' + str(i))
        intended = set(domains)
        matches = rows_by_question.get(question, [])
        hits = matches[0].get(method, {}).get('hits', []) if len(matches) == 1 else []
        valid_hits = [h for h in hits if isinstance(h, dict) and
                      (h.get('domain'), h.get('uri')) in indexed]
        retrieved_domains = {h['domain'] for h in valid_hits}
        gold_concepts = {(c['domain'], c['uri']) for c in item.get('gold_concepts', [])}
        retrieved_concepts = {(h['domain'], h['uri']) for h in valid_hits}
        matching_plans = [p for p in plans if set(p['domains']) == intended]
        row = {
            'id': i, 'question': question,
            'intended_domains_provisional': sorted(intended),
            'retrieved_domains': sorted(retrieved_domains),
            'domain_coverage': intended <= retrieved_domains,
            'gold_concept_coverage': gold_concepts <= retrieved_concepts,
            'retrieval_result_count': len(matches),
            'category': 'multi_domain' if len(intended) > 1 else 'single_domain',
            'matching_catalog_plan_ids': [p['id'] for p in matching_plans],
            'planning_status': None, 'reason': None,
            'sparql': None, 'mapping_status': None,
        }
        if len(intended) == 1:
            row['planning_status'] = 'not_applicable'
            row['reason'] = 'Single-domain question: N-domain planner not applicable'
        elif len(matches) != 1:
            row['planning_status'] = 'abstained'
            row['reason'] = 'Missing or ambiguous retrieval question'
        elif not row['domain_coverage']:
            row['planning_status'] = 'abstained'
            row['reason'] = 'Intended domain absent from retrieved indexed concepts'
        else:
            try:
                plan = compile_n_domain(question, index, catalog, intended,
                                        allow_candidate, limit, _validate_path)
            except ValueError as exc:
                row['planning_status'] = 'abstained'
                row['reason'] = str(exc)
            else:
                row['planning_status'] = 'ready'
                row['sparql'] = plan['sparql']
                row['mapping_status'] = plan['mapping_status']
        rows.append(row)
    multi = [r for r in rows if r['category'] == 'multi_domain']
    counts = Counter(r['planning_status'] for r in rows)
    return {
        'evaluation_type': 'provisional_n_domain_feasibility_and_safety_audit',
        'method': method, 'allow_candidate': allow_candidate,
        'notes': [
            'Expected domains are provisional retrieval annotations, not independently reviewed planning gold.',
            'Domain coverage is not automatic domain-selection accuracy: expected domains are supplied as oracle input.',
            'A ready plan means schema-grounded SPARQL generation, not execution or verified instance identity.',
            'Single-domain questions are out of scope, not planner failures.',
            'Strict-mode abstention is not automatically a correct answer without independent planning labels.',
        ],
        'summary': {
            'total_questions': len(rows),
            'single_domain_out_of_scope': len(rows) - len(multi),
            'multi_domain_questions': len(multi),
            'multi_domain_with_retrieval_coverage': sum(r['domain_coverage'] for r in multi),
            'multi_domain_with_exact_catalog_plan': sum(bool(r['matching_catalog_plan_ids']) for r in multi),
            'multi_domain_ready': sum(r['planning_status'] == 'ready' for r in multi),
            'multi_domain_abstained': sum(r['planning_status'] == 'abstained' for r in multi),
            'statuses': dict(sorted(counts.items())),
            'abstention_reasons': dict(sorted(Counter(
                r['reason'] for r in multi if r['planning_status'] == 'abstained').items())),
        },
        'results': rows,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--gold', type=Path, default=GOLD)
    ap.add_argument('--retrieval', type=Path, default=RETRIEVAL)
    ap.add_argument('--index', type=Path, default=INDEX)
    ap.add_argument('--catalog', type=Path, default=CATALOG)
    ap.add_argument('--method', choices=('hybrid', 'vector', 'lexical'), default='hybrid')
    ap.add_argument('--allow-candidate', action='store_true')
    ap.add_argument('--limit', type=int, default=100)
    ap.add_argument('--output', type=Path, default=BASE / 'data/n_domain_planning_audit_33.json')
    args = ap.parse_args()
    report = evaluate(
        json.loads(args.gold.read_text(encoding='utf-8')),
        json.loads(args.retrieval.read_text(encoding='utf-8')),
        json.loads(args.index.read_text(encoding='utf-8')),
        json.loads(args.catalog.read_text(encoding='utf-8')),
        args.method, args.allow_candidate, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n',
                           encoding='utf-8')
    print(json.dumps(report['summary'], indent=2))
    print('Wrote:', args.output)


if __name__ == '__main__':
    main()
