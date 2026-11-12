"""Experiment 3: retrieval-gated, non-oracle N-domain planning on 16 questions.

Domain selection is a conservative, deterministic explicit-domain-mention
baseline, NOT an LLM or retrieval-only domain selector. It uses no gold labels.
Hybrid/vector/lexical retrieval must independently support every selected domain.
Run from repo root with Ollama embedding server and existing schema vectors.
"""
import argparse
import importlib.util
import json
import re
import urllib.request
from collections import Counter
from pathlib import Path

from semantic.dtwise_cross_domain import _validate_path
from semantic.dtwise_n_domain_planner import compile_n_domain

BASE = Path('experiments/vector_graph_rag')
INDEX = Path('semantic/ontology/dtwise/dtwise-schema-index.json')
CATALOG = Path('semantic/ontology/dtwise/cross-domain-mappings.json')
BENCHMARK = BASE / 'gold/dtwise_n_domain_planning_review_draft.json'
RECORDS = BASE / 'data/schema_records.jsonl'
VECTORS = BASE / 'data/schema_vectors.jsonl'
OUTPUT = BASE / 'data/end_to_end_n_domain_16.json'

# Only unambiguous domain names; do not infer cross-domain identity from concepts.
DOMAIN_PATTERNS = {
    'engineeringbom': r'\b(?:engineering\s*bom|ebom)\b',
    'ecad': r'\becad\b',
    'dexpi': r'\bdexpi\b',
    'assetinventory': r'\b(?:asset\s*inventory|assetinventory)\b',
    'productcatalog': r'\b(?:product\s*catalog|productcatalog)\b',
    'opcuaconnectivity': r'\b(?:opc\s*ua|opcuaconnectivity)\b',
}


def select_explicit_domains(question):
    return sorted(d for d, pattern in DOMAIN_PATTERNS.items()
                  if re.search(pattern, question, re.IGNORECASE))


def load_retriever():
    spec = importlib.util.spec_from_file_location(
        'dtwise_hybrid_retrieval', BASE / '06_evaluate_hybrid_retrieval.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate(benchmark, index, catalog, records, vectors, embed,
             method='hybrid', top_k=10, weight=0.7, limit=100):
    if method not in ('hybrid', 'vector', 'lexical'):
        raise ValueError('Invalid retrieval method')
    if not 0 <= weight <= 1 or top_k < 1:
        raise ValueError('Invalid retrieval parameters')
    retriever = load_retriever()
    indexed = {(c['domain'], c['uri']) for c in index.get('concepts', [])}
    rows = []
    for case in benchmark['cases']:
        question = case['question']
        selected = select_explicit_domains(question)
        ranked, _ = retriever.ranks(records, vectors, question, embed(question), top_k, weight)
        hits = [{'domain': r['domain'], 'uri': r['uri']}
                for r in ranked[method] if (r['domain'], r['uri']) in indexed]
        retrieved = sorted({h['domain'] for h in hits})
        supported = set(selected) <= set(retrieved)
        gold = set(case['expected_domains'])  # scoring only; never planner input
        row = {
            'id': case['id'], 'question': question,
            'selected_domains': selected, 'expected_domains_provisional': sorted(gold),
            'exact_domain_set_match': set(selected) == gold,
            'retrieved_domains': retrieved,
            'selected_domains_supported_by_retrieval': supported,
            'hits': hits, 'modes': {},
        }
        for mode, allow_candidate in [('strict', False), ('exploratory', True)]:
            status, reason, sparql = 'abstained', None, None
            if len(selected) < 2:
                reason = 'Fewer than two explicitly mentioned domains'
            elif not supported:
                reason = 'Selected domains lack indexed top-k retrieval evidence'
            else:
                try:
                    plan = compile_n_domain(question, index, catalog, set(selected),
                                            allow_candidate, limit, _validate_path)
                except ValueError as exc:
                    reason = str(exc)
                else:
                    status, sparql = 'ready', plan['sparql']
            expected = case['expected_' + mode + '_status']
            row['modes'][mode] = {
                'status': status, 'reason': reason, 'sparql': sparql,
                'expected_status_provisional': expected,
                'decision_match': status == expected,
                'end_to_end_match': set(selected) == gold and status == expected,
                'executed': False,
            }
        rows.append(row)
    summary = {
        'total_cases': len(rows),
        'exact_domain_set_matches': sum(r['exact_domain_set_match'] for r in rows),
        'selected_domain_sets_retrieval_supported': sum(
            r['selected_domains_supported_by_retrieval'] for r in rows),
    }
    for mode in ('strict', 'exploratory'):
        summary[mode] = {
            'ready': sum(r['modes'][mode]['status'] == 'ready' for r in rows),
            'abstained': sum(r['modes'][mode]['status'] == 'abstained' for r in rows),
            'decision_matches': sum(r['modes'][mode]['decision_match'] for r in rows),
            'end_to_end_matches': sum(r['modes'][mode]['end_to_end_match'] for r in rows),
            'abstention_reasons': dict(sorted(Counter(
                r['modes'][mode]['reason'] for r in rows
                if r['modes'][mode]['reason']).items())),
        }
    return {
        'evaluation_type': 'retrieval_gated_explicit_domain_baseline',
        'benchmark_status': benchmark.get('status'),
        'retrieval_method': method, 'top_k': top_k, 'vector_weight': weight,
        'limitations': [
            'Explicit-domain-mention baseline; not retrieval-only or LLM intent selection.',
            'Benchmark questions explicitly name domains; results may overestimate performance on implicit questions.',
            'Provisional labels and expectations; not independently reviewed.',
            'No SPARQL execution or verified cross-domain instance identity.',
            'Candidate mode is exploratory only; retrieval evidence never authorizes joins.',
        ],
        'summary': summary, 'results': rows,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--benchmark', type=Path, default=BENCHMARK)
    ap.add_argument('--index', type=Path, default=INDEX)
    ap.add_argument('--catalog', type=Path, default=CATALOG)
    ap.add_argument('--records', type=Path, default=RECORDS)
    ap.add_argument('--vectors', type=Path, default=VECTORS)
    ap.add_argument('--output', type=Path, default=OUTPUT)
    ap.add_argument('--endpoint', default='http://localhost:11434')
    ap.add_argument('--method', choices=('hybrid', 'vector', 'lexical'), default='hybrid')
    ap.add_argument('--top-k', type=int, default=10)
    ap.add_argument('--vector-weight', type=float, default=0.7)
    ap.add_argument('--limit', type=int, default=100)
    args = ap.parse_args()
    retriever = load_retriever()
    records = retriever.load_jsonl(args.records)
    vector_rows = retriever.load_jsonl(args.vectors)
    vectors = {v['id']: v for v in vector_rows}
    if len(vectors) != len(records) or any(r['id'] not in vectors for r in records):
        raise ValueError('Vectors and schema records do not match')
    models = {v['model'] for v in vector_rows}
    if len(models) != 1:
        raise ValueError('Expected exactly one embedding model')
    model = models.pop()

    def embed(question):
        request = urllib.request.Request(
            args.endpoint.rstrip('/') + '/api/embed',
            json.dumps({'model': model, 'input': question}).encode('utf-8'),
            {'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)['embeddings'][0]

    report = evaluate(
        json.loads(args.benchmark.read_text(encoding='utf-8')),
        json.loads(args.index.read_text(encoding='utf-8')),
        json.loads(args.catalog.read_text(encoding='utf-8')),
        records, vectors, embed, args.method, args.top_k, args.vector_weight, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n',
                           encoding='utf-8')
    print(json.dumps(report['summary'], indent=2))
    print('Wrote:', args.output)


if __name__ == '__main__':
    main()
