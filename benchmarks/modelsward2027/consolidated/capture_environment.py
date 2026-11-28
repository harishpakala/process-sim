"""Capture experiment provenance; no model generation or RDF writes."""
import argparse, datetime, hashlib, importlib.metadata, json, os, platform, subprocess, sys
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MODELS = ['qwen2.5-coder:7b', 'llama3.1:8b', 'mistral:7b']

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def command(*args):
    try:
        return subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.STDOUT, timeout=20).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return {'error': str(exc)}

def get_json(url):
    with urlopen(url, timeout=30) as response:
        return json.load(response)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gold', type=Path, required=True)
    p.add_argument('--graphdb-url', required=True)
    p.add_argument('--ollama-url', default='http://127.0.0.1:11434')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('Output already exists')
    gold = json.loads(a.gold.read_text(encoding='utf-8-sig'))
    ref = HERE/'reference_queries_modelsward2027.json'
    if gold.get('scope') != 'all' or gold.get('inference_requested') is not False or gold.get('endpoint') != a.graphdb_url or gold.get('reference_sha256') != digest(ref) or len(gold.get('results', [])) != 50 or any(r.get('status') != 'pass' for r in gold['results']):
        raise ValueError('Full successful gold report for this endpoint required')
    paths = [HERE/n for n in ('benchmark_queries_modelsward2027.json','reference_queries_modelsward2027.json','result_contracts.json','consolidated_ordered_references.json','score_reviewed_runs.py','semantic_review.py')]
    paths += [HERE.parent/n for n in ('run_modelsward_benchmark.py','direct_sparql.py','result_semantics.py','ordered_semantics.py','rejection_semantics.py')]
    paths += [ROOT/'semantic/ontology2/dtwise'/n for n in ('dtwise-schema-index.json','cross-domain-mappings.json')]
    paths += [ROOT/'benchmarks/shacl_phase1/aast_instance_graphs.json']
    paths += sorted((ROOT/'src/process_sim/dtwise/shacl_planner').rglob('*.py'))
    tags = get_json(a.ollama_url.rstrip('/')+'/api/tags')
    installed = {m.get('name'):m for m in tags['models']}
    missing = [m for m in MODELS if not installed.get(m,{}).get('digest')]
    if missing:
        raise ValueError('Missing model digests: '+', '.join(missing))
    packages = {}
    for name in ('rdflib','requests','numpy','pyshacl','process-sim'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    report = {
        'created_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'git_commit': command('git','rev-parse','HEAD'),
        'git_branch': command('git','branch','--show-current'),
        'git_tracked_changes': command('git','status','--porcelain','--untracked-files=no'),
        'environment': {'python':sys.version,'platform':platform.platform(),'machine':platform.machine(),'processor':platform.processor(),'logical_cpus':os.cpu_count(),'packages':packages,'gpu':command('nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader')},
        'ollama': {'endpoint':a.ollama_url,'version':get_json(a.ollama_url.rstrip('/')+'/api/version'),'models':{m:installed[m] for m in MODELS},'embedding_model':installed.get('nomic-embed-text:latest')},
        'graphdb': {'endpoint':a.graphdb_url,'inference_requested':False,'gold_sha256':digest(a.gold),'snapshot_identity_verified':False,'note':'Gold file fingerprint is not a dataset fingerprint. Live snapshot verification remains required.'},
        'file_sha256': {x.relative_to(ROOT).as_posix():digest(x) for x in paths},
        'experiment': {'methods':['direct','ablated','full'],'models':MODELS,'queries':275,'attempts':2475,'retrieval':'expanded','graphdb_timeout_seconds':60,'model_settings_note':'Inspect and record effective transport options separately; this utility does not change them.'}
    }
    with a.output.open('x',encoding='utf-8') as f:
        json.dump(report,f,indent=2)
        f.write('\n')
    print('Saved',a.output)
    print('Model digests captured:',len(MODELS))
    print('Files fingerprinted:',len(report['file_sha256']))
    print('Dataset snapshot verification: pending')

if __name__ == '__main__':
    main()
