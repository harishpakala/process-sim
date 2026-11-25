"""Run the existing Phase-1 benchmark against multiple Ollama models."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=Path.cwd())
    p.add_argument('--benchmark', type=Path, default=Path('benchmarks/shacl_phase1/benchmark_queries.json'))
    p.add_argument('--models', nargs='+', default=['qwen2.5-coder:7b', 'llama3.1:8b', 'mistral:7b'])
    p.add_argument('--retrieval', choices=['exact', 'semantic', 'expanded'], default='expanded')
    p.add_argument('--endpoint', default='http://127.0.0.1:11434')
    p.add_argument('--output-dir', type=Path, default=Path('benchmark_results/smoke'))
    p.add_argument('--execute-graphdb', action='store_true')
    p.add_argument('--graphdb-endpoint', default='http://localhost:7200/repositories/AAST')
    a = p.parse_args()
    repo = a.repo.resolve()
    benchmark = (repo / a.benchmark).resolve()
    output = (repo / a.output_dir).resolve()
    if not (repo / 'benchmarks/shacl_phase1/run_all.py').is_file():
        p.error('--repo must point to the process-sim repository')
    data = json.loads(benchmark.read_text(encoding='utf-8-sig'))
    scenarios = data['scenarios']
    ids = [v['id'] for s in scenarios for v in s['paraphrases']]
    counts = [sum(len(s['paraphrases']) for s in scenarios if s['scenario_id'].startswith(prefix)) for prefix in ('SD', 'CD')]
    if len(scenarios) != 20 or len(ids) != 100 or len(set(ids)) != 100 or counts != [70, 30]:
        p.error('Current run_all.py requires 20 scenarios and 100 unique questions (70 SD / 30 CD). Adapt the runner before using a smaller or ModelsWard manifest.')
    output.mkdir(parents=True, exist_ok=True)
    summary = []
    for i, model in enumerate(a.models, 1):
        slug = ''.join(c if c.isalnum() or c in '-_.' else '_' for c in model)
        target = output / f'{i:02d}_{slug}'
        target.mkdir(exist_ok=False)
        cmd = [sys.executable, '-m', 'benchmarks.shacl_phase1.run_all', '--benchmark', str(benchmark), '--model', model, '--retrieval', a.retrieval, '--endpoint', a.endpoint, '--output-dir', str(target)]
        if a.execute_graphdb:
            cmd += ['--execute-graphdb', '--graphdb-endpoint', a.graphdb_endpoint]
        print(f'\n=== {model} ===', flush=True)
        start = time.perf_counter()
        result = subprocess.run(cmd, cwd=repo, check=False)
        row = {'model': model, 'retrieval': a.retrieval, 'exit_code': result.returncode, 'seconds': round(time.perf_counter()-start, 2), 'output_dir': str(target)}
        path = target / 'summary.json'
        if path.is_file():
            row['benchmark_summary'] = json.loads(path.read_text(encoding='utf-8'))
        summary.append(row)
        (output / 'model_comparison.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return int(any(r['exit_code'] != 0 for r in summary))


if __name__ == '__main__':
    raise SystemExit(main())
