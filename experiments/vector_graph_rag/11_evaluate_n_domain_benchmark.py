"""Evaluate provisional N-domain benchmark in strict and exploratory modes.

Run: python -m experiments.vector_graph_rag.11_evaluate_n_domain_benchmark
This is an oracle-domain, catalog-grounded planning test, not an end-to-end
natural-language domain selection or instance-identity evaluation.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from semantic.dtwise_cross_domain import _validate_path
from semantic.dtwise_n_domain_planner import compile_n_domain, _normalize

BASE = Path('experiments/vector_graph_rag')
DEFAULT_BENCHMARK = BASE / 'gold/dtwise_n_domain_planning_review_draft.json'
DEFAULT_INDEX = Path('semantic/ontology/dtwise/dtwise-schema-index.json')
DEFAULT_CATALOG = Path('semantic/ontology/dtwise/cross-domain-mappings.json')
DEFAULT_OUTPUT = BASE / 'data/n_domain_benchmark_report.json'


def evaluate(benchmark, index, catalog, limit=100):
    cases = benchmark['cases']
    ids = [c['id'] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate benchmark IDs')
    plans = _normalize(catalog)
    results = []
    for case in cases:
        domains = case['expected_domains']
        if len(domains) < 2 or len(set(domains)) != len(domains):
            raise ValueError('Expected at least two unique domains for ' + case['id'])
        exact = [p for p in plans if set(p['domains']) == set(domains)]
        row = {
            'id': case['id'],
            'question': case['question'],
            'expected_domains_provisional': domains,
            'category': case['category'],
            'review_status': case.get('review_status'),
            'exact_catalog_plan_ids': [p['id'] for p in exact],
            'modes': {},
        }
        for mode, allow_candidate in [('strict', False), ('exploratory', True)]:
            expected = case['expected_' + mode + '_status']
            try:
                plan = compile_n_domain(case['question'], index, catalog,
                                        set(domains), allow_candidate, limit,
                                        _validate_path)
            except ValueError as exc:
                status, reason, sparql, mapping_status = 'abstained', str(exc), None, None
            else:
                status, reason = 'ready', None
                sparql, mapping_status = plan['sparql'], plan['mapping_status']
            row['modes'][mode] = {
                'status': status,
                'expected_status_provisional': expected,
                'matches_expected_status': status == expected,
                'reason': reason,
                'sparql': sparql,
                'mapping_status': mapping_status,
                'executed': False,
            }
        results.append(row)
    summary = {
        'total_cases': len(results),
        'cataloged_candidate_cases': sum(r['category'] == 'cataloged_candidate' for r in results),
        'uncataloged_cases': sum(r['category'] == 'uncataloged' for r in results),
        'strict': {
            'ready': sum(r['modes']['strict']['status'] == 'ready' for r in results),
            'abstained': sum(r['modes']['strict']['status'] == 'abstained' for r in results),
            'provisional_expectation_matches': sum(r['modes']['strict']['matches_expected_status'] for r in results),
        },
        'exploratory': {
            'ready': sum(r['modes']['exploratory']['status'] == 'ready' for r in results),
            'abstained': sum(r['modes']['exploratory']['status'] == 'abstained' for r in results),
            'provisional_expectation_matches': sum(r['modes']['exploratory']['matches_expected_status'] for r in results),
        },
        'reasons_by_mode': {
            mode: dict(sorted(Counter(
                r['modes'][mode]['reason'] for r in results
                if r['modes'][mode]['reason']).items()))
            for mode in ('strict', 'exploratory')
        },
    }
    return {
        'benchmark_status': benchmark.get('status'),
        'evaluation_type': 'oracle_domain_governed_n_domain_planning',
        'limitations': [
            'Questions and expected outcomes are provisional and require independent review.',
            'Expected domain sets are supplied to the planner, not predicted by retrieval.',
            'Exploratory ready status is not semantic mapping approval.',
            'No SPARQL was executed against an instance dataset.',
        ],
        'summary': summary, 'results': results,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--benchmark', type=Path, default=DEFAULT_BENCHMARK)
    ap.add_argument('--index', type=Path, default=DEFAULT_INDEX)
    ap.add_argument('--catalog', type=Path, default=DEFAULT_CATALOG)
    ap.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument('--limit', type=int, default=100)
    args = ap.parse_args()
    report = evaluate(
        json.loads(args.benchmark.read_text(encoding='utf-8')),
        json.loads(args.index.read_text(encoding='utf-8')),
        json.loads(args.catalog.read_text(encoding='utf-8')), args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n',
                           encoding='utf-8')
    print(json.dumps(report['summary'], indent=2))
    print('Wrote:', args.output)


if __name__ == '__main__':
    main()
