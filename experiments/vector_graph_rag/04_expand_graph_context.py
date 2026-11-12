"""Expand retrieval hits using ONLY explicit, same-domain OWL/SHACL schema evidence.

No traversal of shared names, no instance triples, and no cross-domain joins.
"""
import argparse
import json
from collections import defaultdict, deque
from pathlib import Path

SH = 'http://www.w3.org/ns/shacl#'
OWL_RDFS = {
    'http://www.w3.org/2000/01/rdf-schema#domain',
    'http://www.w3.org/2000/01/rdf-schema#range',
    'http://www.w3.org/2000/01/rdf-schema#subClassOf',
    'http://www.w3.org/2002/07/owl#equivalentClass',
    'http://www.w3.org/2002/07/owl#equivalentProperty',
}
SHACL = {SH + x for x in ('property', 'path', 'node', 'targetClass', 'class', 'datatype', 'nodeKind')}
ALLOWED = OWL_RDFS | SHACL


def expand(index, hits, max_hops=2, max_edges=120):
    """Return grounded edges reachable from seed IRIs, scoped by source domain.

    `max_hops` is measured over explicit schema statements. SHACL paths are
    attached independently as evidence; they are not asserted as instance edges.
    """
    if max_hops < 0 or max_edges < 0:
        raise ValueError('max_hops and max_edges must be nonnegative')
    adjacency = defaultdict(list)
    for e in index.get('relationships', []):
        if e.get('predicate') not in ALLOWED or not e.get('domain'):
            continue
        for endpoint in ('subject', 'object'):
            adjacency[(e['domain'], e[endpoint])].append(e)
    for edges in adjacency.values():
        edges.sort(key=lambda e: (e['subject'], e['predicate'], e['object'], e.get('id', '')))

    seeds = sorted({(h['domain'], h['uri']) for h in hits if h.get('domain') and h.get('uri')})
    queue = deque((domain, uri, 0) for domain, uri in seeds)
    seen = set(seeds)
    edges_found = {}
    while queue and len(edges_found) < max_edges:
        domain, uri, depth = queue.popleft()
        if depth >= max_hops:
            continue
        for edge in adjacency.get((domain, uri), []):
            key = (edge['domain'], edge['subject'], edge['predicate'], edge['object'], edge.get('id', ''))
            if key not in edges_found:
                if len(edges_found) >= max_edges:
                    break
                edges_found[key] = edge
            for next_uri in (edge['subject'], edge['object']):
                state = (domain, next_uri)
                if state not in seen:
                    seen.add(state)
                    queue.append((domain, next_uri, depth + 1))

    # Include only SHACL path declarations directly associated with a seed
    # property, or whose owning shape was reached via an explicit schema edge.
    seed_set = set(seeds)
    paths = []
    for p in index.get('shape_paths', []):
        domain = p.get('domain')
        if (domain, p.get('path')) in seed_set or (domain, p.get('node_shape')) in seen:
            paths.append(p)
    paths.sort(key=lambda p: (p['domain'], p['node_shape'], p['path'], p['property_shape']))

    return {
        'seed_concepts': [{'domain': d, 'uri': u} for d, u in seeds],
        'reached_concepts': [{'domain': d, 'uri': u} for d, u in sorted(seen)],
        'schema_edges': sorted(edges_found.values(), key=lambda e: (e['domain'], e['subject'], e['predicate'], e['object'])),
        'shape_paths': paths,
        'safety': {
            'schema_evidence_only': True,
            'cross_domain_joins_verified': False,
            'instance_relationships_inferred': False,
            'note': 'Edges and paths describe ontology/SHACL declarations, not executable instance joins.',
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--index', type=Path, default=Path('semantic/ontology/dtwise/dtwise-schema-index.json'))
    ap.add_argument('--retrieval', type=Path, default=Path('experiments/vector_graph_rag/data/retrieval_results.json'))
    ap.add_argument('--output', type=Path, default=Path('experiments/vector_graph_rag/data/expanded_context.json'))
    ap.add_argument('--method', choices=['vector', 'lexical'], default='vector')
    ap.add_argument('--max-hops', type=int, default=2)
    ap.add_argument('--max-edges', type=int, default=120)
    args = ap.parse_args()
    index = json.loads(args.index.read_text(encoding='utf-8'))
    retrieval = json.loads(args.retrieval.read_text(encoding='utf-8'))
    output = {'method': args.method, 'max_hops': args.max_hops, 'results': []}
    for item in retrieval['results']:
        context = expand(index, item[args.method]['hits'], args.max_hops, args.max_edges)
        output['results'].append({'question': item['question'], 'expected_domains': item.get('expected_domains', []), **context})
        print(f"{item['question']}: {len(context['schema_edges'])} explicit edges, {len(context['shape_paths'])} SHACL paths")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Wrote:', args.output)


if __name__ == '__main__':
    main()
