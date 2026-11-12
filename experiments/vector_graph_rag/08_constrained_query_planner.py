"""DTWise constrained schema-to-SPARQL planner v1.

Read-only single-predicate SELECT. No inferred joins, subject typing, or execution.
"""
import argparse
import json
from pathlib import Path

DEFAULT_INDEX = Path('semantic/ontology/dtwise/dtwise-schema-index.json')
DEFAULT_RETRIEVAL = Path('experiments/vector_graph_rag/data/hybrid_evaluation_33_v3.json')

def plan(index, question, selected, retrieved_hits=None, require_retrieved=True, requested_domains=None):
    """selected: list of {'domain': ..., 'uri': ...}; never infer selection from wording."""
    result = {
        'version': 'dtwise-query-plan-v1',
        'question': question,
        'selected_concepts': selected,
        'status': 'abstained',
        'reason': None,
        'triple_patterns': [],
        'evidence': [],
        'sparql': None,
        'safety': {
            'schema_only_validation': True,
            'instance_relationships_inferred': False,
            'cross_domain_joins_verified': False,
            'query_executed': False,
        },
    }
    def abstain(reason):
        result['reason'] = reason
        return result
    if not question.strip():
        return abstain('Question must not be empty')
    if requested_domains and len(set(requested_domains)) > 1:
        return abstain('Cross-domain question requires verified identity mappings; v1 does not join domains')
    if requested_domains is None or not requested_domains:
        return abstain('Explicit intended domain scope required; planner does not infer question intent')
    if len(selected) != 1:
        return abstain('V1 supports exactly one explicitly selected property; no joins or multi-property queries')
    item = selected[0]
    domain, uri = item.get('domain'), item.get('uri')
    if domain not in set(requested_domains):
        return abstain('Selected predicate is outside the declared question domain scope')
    if not isinstance(domain, str) or not isinstance(uri, str):
        return abstain('Domain and URI are required')
    if not (uri.startswith('https://') or uri.startswith('http://')) or any(c in uri for c in '<>"{}\\\n\r\t '):
        return abstain('Invalid absolute HTTP(S) predicate IRI')
    concepts = [c for c in index.get('concepts', []) if c.get('domain') == domain and c.get('uri') == uri and c.get('kind') == 'property']
    if len(concepts) != 1:
        return abstain('Selected predicate is not a unique indexed property in the specified domain')
    if require_retrieved:
        if retrieved_hits is None:
            return abstain('Retrieval evidence required; supply matching question and retrieval output')
        if (domain, uri) not in {(h.get('domain'), h.get('uri')) for h in retrieved_hits}:
            return abstain('Selected predicate is not among the retrieved hits')
    paths = [p for p in index.get('shape_paths', []) if p.get('domain') == domain and p.get('path') == uri]
    edges = {(e.get('domain'), e.get('id')): e for e in index.get('relationships', [])}
    validated = []
    for p in paths:
        evidence = [edges.get((domain, eid)) for eid in p.get('evidence', [])]
        if not evidence or any(e is None for e in evidence):
            continue
        if not any(e['predicate'] == 'http://www.w3.org/ns/shacl#path'
                   and e['subject'] == p['property_shape'] and e['object'] == uri for e in evidence):
            continue
        validated.append(p)
    if not validated:
        return abstain('No SHACL property path with resolvable supporting declarations')
    # Do not infer a subject rdf:type or connect this pattern to any other domain.
    result['status'] = 'ready'
    result['reason'] = None
    result['triple_patterns'] = [{'subject': '?subject', 'predicate': uri, 'object': '?value', 'domain': domain}]
    result['evidence'] = [{
        'domain': domain,
        'node_shape': p['node_shape'],
        'property_shape': p['property_shape'],
        'path': p['path'],
        'relationship_ids': p['evidence'],
        'evidence_type': 'SHACL schema declaration',
    } for p in validated]
    result['sparql'] = 'SELECT DISTINCT ?subject ?value WHERE {\n  ?subject <' + uri + '> ?value .\n} LIMIT 100'
    result['limitations'] = [
        'Schema evidence validates the predicate, not the existence of matching instance triples.',
        'No rdf:type constraint is added without a separately justified instance class mapping.',
        'This plan is read-only and is not executed by the planner.',
    ]
    return result

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--index', type=Path, default=DEFAULT_INDEX)
    ap.add_argument('--retrieval', type=Path, default=DEFAULT_RETRIEVAL)
    ap.add_argument('--question', required=True, help='Exact question from retrieval results')
    ap.add_argument('--domain', required=True)
    ap.add_argument('--requested-domain', action='append', required=True,
                    help='Explicit intended domain(s); repeat for cross-domain questions (which abstain)')
    ap.add_argument('--concept', required=True, help='Full predicate IRI, explicitly selected')
    ap.add_argument('--output', type=Path, default=Path('experiments/vector_graph_rag/data/query_plan_v1.json'))
    args = ap.parse_args()
    index = json.loads(args.index.read_text(encoding='utf-8'))
    retrieval = json.loads(args.retrieval.read_text(encoding='utf-8'))
    matches = [r for r in retrieval.get('results', []) if r.get('question') == args.question]
    if len(matches) != 1:
        result = {'status': 'abstained', 'reason': 'Question not uniquely found in retrieval results', 'question': args.question, 'sparql': None}
    else:
        result = plan(index, args.question, [{'domain': args.domain, 'uri': args.concept}],
                      matches[0].get('hybrid', {}).get('hits', []),
                      requested_domains=args.requested_domain)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'reason': result.get('reason'), 'sparql': result.get('sparql')}, indent=2))
    print('Wrote:', args.output)

if __name__ == '__main__':
    main()
