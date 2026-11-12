"""Bridge hybrid-retrieved domains to the existing governed DTWise N-domain planner.

Retrieval is candidate discovery, never proof of an identity mapping. The caller
must explicitly select the domain set; no domains are silently added or dropped.
"""
import argparse
import json
from pathlib import Path

from semantic.dtwise_cross_domain import _validate_path
from semantic.dtwise_n_domain_planner import compile_n_domain

ROOT = Path('experiments/vector_graph_rag/data')
INDEX = Path('semantic/ontology/dtwise/dtwise-schema-index.json')
CATALOG = Path('semantic/ontology/dtwise/cross-domain-mappings.json')


def adapt(question, retrieval, index, catalog, requested_domains, method='hybrid',
          allow_candidate=False, limit=100):
    result = {
        'version': 'dtwise-retrieval-n-domain-adapter-v1',
        'question': question,
        'retrieval_method': method,
        'requested_domains': sorted(set(requested_domains)),
        'retrieved_domains': [],
        'status': 'abstained',
        'reason': None,
        'plan': None,
        'safety': {
            'retrieval_is_not_join_evidence': True,
            'join_approval_required_by_default': not allow_candidate,
            'instance_relationships_inferred': False,
            'query_executed': False,
        },
    }
    def abstain(reason):
        result['reason'] = reason
        return result
    if not isinstance(question, str) or not question.strip():
        return abstain('Question required')
    if method not in ('hybrid', 'vector', 'lexical'):
        return abstain('Unsupported retrieval method')
    if not isinstance(requested_domains, (list, tuple)) or len(requested_domains) < 2:
        return abstain('Explicit selection of at least two domains required')
    if any(not isinstance(d, str) or not d for d in requested_domains):
        return abstain('Invalid domain selection')
    if len(set(requested_domains)) != len(requested_domains):
        return abstain('Duplicate selected domains')
    matches = [r for r in retrieval.get('results', []) if r.get('question') == question]
    if len(matches) != 1:
        return abstain('Question must match exactly one retrieval result')
    hits = matches[0].get(method, {}).get('hits')
    if not isinstance(hits, list):
        return abstain('Retrieval hits missing for selected method')
    indexed_domains = {c['domain'] for c in index.get('concepts', [])}
    found = {h.get('domain') for h in hits if isinstance(h, dict) and
             h.get('domain') in indexed_domains and
             any(c.get('domain') == h.get('domain') and c.get('uri') == h.get('uri')
                 for c in index.get('concepts', []))}
    result['retrieved_domains'] = sorted(found)
    requested = set(requested_domains)
    if not requested <= indexed_domains:
        return abstain('Selected domain absent from schema index')
    if not requested <= found:
        return abstain('One or more selected domains lack retrieval evidence in top-k hits')
    # Extra retrieved domains are ranking noise, not implicit additions to the join.
    try:
        plan = compile_n_domain(question, index, catalog, requested,
                                allow_candidate, limit, _validate_path)
    except ValueError as exc:
        return abstain(str(exc))
    result['status'] = 'ready'
    result['plan'] = plan
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--question', required=True)
    ap.add_argument('--domain', action='append', required=True,
                    help='Explicit intended domain; repeat for each domain')
    ap.add_argument('--retrieval', type=Path, default=ROOT / 'hybrid_evaluation_33_v3.json')
    ap.add_argument('--index', type=Path, default=INDEX)
    ap.add_argument('--catalog', type=Path, default=CATALOG)
    ap.add_argument('--method', choices=('hybrid', 'vector', 'lexical'), default='hybrid')
    ap.add_argument('--allow-candidate', action='store_true',
                    help='Explicit exploratory opt-in for unapproved catalog mappings')
    ap.add_argument('--limit', type=int, default=100)
    ap.add_argument('--output', type=Path, default=ROOT / 'n_domain_adapter_result.json')
    args = ap.parse_args()
    result = adapt(args.question,
                   json.loads(args.retrieval.read_text(encoding='utf-8')),
                   json.loads(args.index.read_text(encoding='utf-8')),
                   json.loads(args.catalog.read_text(encoding='utf-8')),
                   args.domain, args.method, args.allow_candidate, args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n',
                           encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print('Wrote:', args.output)


if __name__ == '__main__':
    main()
