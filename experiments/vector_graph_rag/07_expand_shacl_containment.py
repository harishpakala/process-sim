"""Attach explicitly declared SHACL parent/child paths to retrieved schema hits.

This is context augmentation, not retrieval reranking or instance-join inference.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

SH_NODE = 'http://www.w3.org/ns/shacl#node'

def build_links(index):
    # A parent property shape sh:node child node shape, together with
    # shape_paths, is sufficient to establish a schema-level containment link.
    paths = index.get('shape_paths', [])
    by_property = defaultdict(list)
    by_node = defaultdict(list)
    for path in paths:
        by_property[(path['domain'], path['property_shape'])].append(path)
        by_node[(path['domain'], path['node_shape'])].append(path)
    links = defaultdict(list)
    for edge in index.get('relationships', []):
        if edge.get('predicate') != SH_NODE:
            continue
        domain = edge.get('domain')
        for parent in by_property.get((domain, edge.get('subject')), []):
            for child in by_node.get((domain, edge.get('object')), []):
                if parent['path'] == child['path']:
                    continue
                evidence = {
                    'domain': domain,
                    'parent_uri': parent['path'],
                    'child_uri': child['path'],
                    'parent_property_shape': parent['property_shape'],
                    'child_node_shape': child['node_shape'],
                    'sh_node_edge': edge.get('id'),
                    'relation': 'declared_shacl_containment',
                }
                links[(domain, parent['path'])].append((domain, child['path'], evidence))
                links[(domain, child['path'])].append((domain, parent['path'], evidence))
    return links

def augment(index, hits):
    links = build_links(index)
    seeds = {(hit['domain'], hit['uri']) for hit in hits}
    related = {}
    for key in sorted(seeds):
        for domain, uri, evidence in links.get(key, []):
            if (domain, uri) in seeds:
                continue
            related[(domain, uri, evidence['parent_uri'], evidence['child_uri'])] = {
                'domain': domain, 'uri': uri, 'evidence': evidence,
                'origin_seed': {'domain': key[0], 'uri': key[1]},
            }
    return {
        'retrieved_hits': hits,
        'additional_schema_context': [related[k] for k in sorted(related)],
        'safety': {
            'schema_evidence_only': True,
            'instance_relationships_inferred': False,
            'cross_domain_joins_verified': False,
        },
    }

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--index', type=Path, default=Path('semantic/ontology/dtwise/dtwise-schema-index.json'))
    ap.add_argument('--evaluation', type=Path, default=Path('experiments/vector_graph_rag/data/hybrid_evaluation_33_v2.json'))
    ap.add_argument('--method', choices=['vector','lexical','hybrid'], default='hybrid')
    ap.add_argument('--output', type=Path, default=Path('experiments/vector_graph_rag/data/hybrid_shacl_context.json'))
    args = ap.parse_args()
    index = json.loads(args.index.read_text(encoding='utf-8'))
    evaluation = json.loads(args.evaluation.read_text(encoding='utf-8'))
    rows = []
    for item in evaluation['results']:
        context = augment(index, item[args.method]['hits'])
        rows.append({'question': item['question'], **context})
    output = {'method': args.method, 'note': 'Context only: retrieval rankings and metrics are unchanged.', 'results': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Wrote:', args.output)

if __name__ == '__main__':
    main()
