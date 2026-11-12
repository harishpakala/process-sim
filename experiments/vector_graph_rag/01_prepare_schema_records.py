"""Create reproducible, schema-only embedding records from the DTWise JSON index."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def local(uri):
    return re.split(r'[/#]', uri)[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--index', type=Path, default=Path('semantic/ontology/dtwise/dtwise-schema-index.json'))
    ap.add_argument('--output', type=Path, default=Path('experiments/vector_graph_rag/data/schema_records.jsonl'))
    args = ap.parse_args()
    index = json.loads(args.index.read_text(encoding='utf-8'))
    # The authored EngineeringBOM template contains a BOMItemRecord description
    # that is absent from some previously generated schema indexes. Reuse only
    # that exact authored description; do not synthesize schema semantics.
    template_path = Path('semantic/templates/engineeringbom_v2_template.json')
    template_descriptions = {}
    if template_path.exists():
        template = json.loads(template_path.read_text(encoding='utf-8'))
        def visit(value):
            if isinstance(value, dict):
                if value.get('idShort') == 'BOMItemRecord':
                    template_descriptions['BOMItemRecord'] = [
                        entry['text'] for entry in value.get('description', [])
                        if entry.get('language') == 'en' and entry.get('text')
                    ]
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        visit(template)
    records = []
    for concept in index['concepts']:
        if concept['kind'] not in ('class', 'property'):
            continue
        domain, uri = concept['domain'], concept['uri']
        paths = sorted({p['node_shape'] for p in index.get('shape_paths', [])
                        if p['domain'] == domain and p['path'] == uri})
        descriptions = concept.get('descriptions', [])\n        if (not descriptions and domain == 'engineeringbom'\n                and uri == 'https://example.org/engineeringbom/hasBOMItemRecord'):\n            descriptions = template_descriptions.get('BOMItemRecord', [])\n        parts = [f"Ontology {concept['kind']}: {local(uri)}",
                 'Labels: ' + '; '.join(concept.get('labels', [])),
                 'Descriptions: ' + '; '.join(descriptions),
                 'SHACL owning shapes: ' + '; '.join(local(p) for p in paths)]
        text = '\n'.join(p for p in parts if not p.endswith(': '))
        key = f'{domain}|{concept["kind"]}|{uri}'
        records.append({'id': hashlib.sha256(key.encode()).hexdigest()[:20],
                        'uri': uri, 'domain': domain, 'kind': concept['kind'],
                        'text': text, 'shape_owners': paths})
    # Relationships are indexed separately: never interpret an edge as an instance fact.
    for edge in index.get('ontology_edges', []):
        key = '|'.join(str(edge.get(k, '')) for k in ('domain', 'subject', 'predicate', 'object'))
        records.append({'id': hashlib.sha256(('edge|' + key).encode()).hexdigest()[:20],
                        'domain': edge['domain'], 'kind': 'schema_edge',
                        'uri': edge['predicate'], 'subject': edge['subject'], 'object': edge['object'],
                        'text': f"Ontology schema statement: {local(edge['subject'])} {local(edge['predicate'])} {local(edge['object'])}."})
    records.sort(key=lambda x: (x['domain'], x['kind'], x['uri'], x['id']))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(''.join(json.dumps(x, ensure_ascii=False, sort_keys=True) + '\n' for x in records), encoding='utf-8')
    print(json.dumps({'records': len(records), 'output': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()
