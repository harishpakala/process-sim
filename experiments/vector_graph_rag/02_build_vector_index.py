"""Embed schema records with Ollama; JSONL vectors avoid a database dependency."""
import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path


def embed(texts, model, endpoint, timeout):
    payload = json.dumps({'model': model, 'input': texts}).encode('utf-8')
    req = urllib.request.Request(endpoint.rstrip('/') + '/api/embed', payload,
                                 {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        result = json.load(response)
    vectors = result.get('embeddings')
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise ValueError('Unexpected Ollama embedding response; check model and /api/embed compatibility')
    return vectors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--records', type=Path, default=Path('experiments/vector_graph_rag/data/schema_records.jsonl'))
    ap.add_argument('--output', type=Path, default=Path('experiments/vector_graph_rag/data/schema_vectors.jsonl'))
    ap.add_argument('--model', default='nomic-embed-text')
    ap.add_argument('--endpoint', default='http://localhost:11434')
    ap.add_argument('--batch-size', type=int, default=16)
    ap.add_argument('--timeout', type=int, default=120)
    args = ap.parse_args()
    if args.batch_size < 1:
        ap.error('--batch-size must be positive')
    records = [json.loads(s) for s in args.records.read_text(encoding='utf-8').splitlines() if s.strip()]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dimension = None
    try:
        with args.output.open('w', encoding='utf-8') as out:
            for offset in range(0, len(records), args.batch_size):
                batch = records[offset:offset + args.batch_size]
                vectors = embed([x['text'] for x in batch], args.model, args.endpoint, args.timeout)
                for record, vector in zip(batch, vectors):
                    if not vector or not all(isinstance(v, (float, int)) for v in vector):
                        raise ValueError('Invalid embedding vector')
                    dimension = dimension or len(vector)
                    if len(vector) != dimension:
                        raise ValueError('Inconsistent embedding dimensions')
                    out.write(json.dumps({'id': record['id'], 'model': args.model, 'embedding': vector}) + '\n')
                print(f'Embedded {min(offset + len(batch), len(records))}/{len(records)}')
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SystemExit(f'Ollama unavailable: {exc}. Start Ollama and pull model {args.model}.') from exc
    print(json.dumps({'count': len(records), 'dimensions': dimension, 'model': args.model, 'output': str(args.output)}))


if __name__ == '__main__':
    main()
