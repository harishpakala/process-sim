"""Compare schema vector retrieval with the existing token-postings baseline."""
import argparse
import json
import math
import re
import urllib.request
from pathlib import Path


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def cosine(a, b):
    if len(a) != len(b):
        raise ValueError('Embedding dimension mismatch')
    na = math.sqrt(sum(x*x for x in a)); nb = math.sqrt(sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b)) / (na*nb) if na and nb else 0.0


def tokens(s):
    return set(re.findall(r'[a-z0-9]+', re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', s).lower()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--records', type=Path, default=Path('experiments/vector_graph_rag/data/schema_records.jsonl'))
    ap.add_argument('--vectors', type=Path, default=Path('experiments/vector_graph_rag/data/schema_vectors.jsonl'))
    ap.add_argument('--questions', type=Path, default=Path('experiments/vector_graph_rag/questions.example.json'))
    ap.add_argument('--output', type=Path, default=Path('experiments/vector_graph_rag/data/retrieval_results.json'))
    ap.add_argument('--endpoint', default='http://localhost:11434')
    ap.add_argument('--top-k', type=int, default=10)
    args = ap.parse_args()
    records = load_jsonl(args.records)
    vectors = {v['id']: v for v in load_jsonl(args.vectors)}
    if len(vectors) != len(records) or any(r['id'] not in vectors for r in records):
        raise ValueError('Vectors do not match records; rebuild embeddings')
    models = {v['model'] for v in vectors.values()}
    if len(models) != 1:
        raise ValueError('Mixed embedding models')
    model = models.pop()
    questions = json.loads(args.questions.read_text(encoding='utf-8'))
    results = []
    for item in questions:
        q = item['question']
        payload = json.dumps({'model': model, 'input': q}).encode()
        req = urllib.request.Request(args.endpoint.rstrip('/') + '/api/embed', payload,
                                     {'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=120) as response:
            qv = json.load(response)['embeddings'][0]
        vector_rank = sorted(records, key=lambda r: (-cosine(qv, vectors[r['id']]['embedding']), r['id']))
        lexical_rank = sorted(records, key=lambda r: (-len(tokens(q) & tokens(r['text'])), r['id']))
        # Do not count zero-overlap lexical hits as retrieved evidence.
        lexical_rank = [r for r in lexical_rank if tokens(q) & tokens(r['text'])]
        expected = set(item.get('expected_domains', []))
        row = {'question': q, 'expected_domains': sorted(expected)}
        for label, ranked in [('vector', vector_rank), ('lexical', lexical_rank)]:
            top = ranked[:args.top_k]
            found = {r['domain'] for r in top}
            row[label] = {'hits': [{'id': r['id'], 'uri': r['uri'], 'kind': r['kind'], 'domain': r['domain']} for r in top],
                          'domain_recall_at_k': len(expected & found)/len(expected) if expected else None,
                          'retrieved_domains': sorted(found)}
        results.append(row)
        print(f"{q}\n  vector recall: {row['vector']['domain_recall_at_k']} | lexical recall: {row['lexical']['domain_recall_at_k']}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'model': model, 'top_k': args.top_k, 'results': results}, indent=2), encoding='utf-8')
    print('Wrote:', args.output)


if __name__ == '__main__':
    main()
