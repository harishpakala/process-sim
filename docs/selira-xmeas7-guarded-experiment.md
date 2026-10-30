# SELiRA XMEAS7 guarded experiment (experimental)

This is a **snapshot-driven, fail-closed prototype**, not authenticated DEXPI/ECAD/PLC/OPC UA or live GraphDB integration. It does not modify the existing asset/product Q&A CLI or production API.

## Run deterministic tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_selira_engineering_gate.py' -v
```

## Inputs

The gate requires a JSON evidence snapshot with `revision`, `lifecycle=CURRENT`, `runId`, `coverage=[start,end]`, and exactly one `paths` entry. The path must provide `property`, `signal=XMEAS7`, `engineeringQuantityKind`, `signalQuantityKind`, `engineeringUnit`, `signalUnit`, and `nodes` for `DEXPI`, `ECAD`, `PLC`, `OPCUA`, `TEP`. Four ordered `edges` must contain matching `from`, `to`, nonempty `evidence`, and matching `revision`. A consumer task supplies `revision`, `runId`, `interval`, `property`, `signal`, and `question`.

To generate a local **synthetic** sample, run:

```bash
PYTHONPATH=src python - <<'PY'
import json
from tests.test_selira_engineering_gate import fixture
snapshot, task = fixture()
open('/tmp/selira-snapshot.json','w').write(json.dumps(snapshot,indent=2))
open('/tmp/selira-task.json','w').write(json.dumps(task,indent=2))
PY
```

If `tests` is not importable as a package, load the fixture with `runpy.run_path('tests/test_selira_engineering_gate.py')['fixture']()`.

Run the guard without Ollama:

```bash
PYTHONPATH=src python scripts/ask_selira_guarded_ollama.py --snapshot /tmp/selira-snapshot.json --task /tmp/selira-task.json --evidence-only
```

With Ollama running, omit `--evidence-only`. The guarded CLI checks engineering evidence **before** calling Ollama. It also requires a revision-matched, time-bounded numeric `observation` in the snapshot. A withheld request exits with code 2.

## Boundaries

- Unit checking tests dimensional compatibility, **not** numeric conversion or calibration. Pressure conversions require an explicit downstream conversion when units differ.
- Snapshot edge references are supplied assertions; their authenticity and source revision are **not** independently checked against GraphDB.
- No actual reactor-pressure association with XMEAS7 is established by the synthetic fixture.
- The prototype is not integrated into `scripts/ask_graphdb_ollama.py`, production HTTP endpoints, or historian queries.
- A model answer is not numerically verified after generation. For claim-correctness experiments, compare the response with the snapshot observation.
- The test suite is deterministic and synthetic; do not report it as live industrial validation.

## Suggested evaluation

Compare ungated, evidence-grounded, and guarded pipelines on identical questions and reviewed snapshots. Include correct, wrong-quantity, wrong-unit, duplicate mapping, missing edge, stale revision, and inadequate coverage cases. Report wrong-use and over-withholding separately. The next integration step is to replace the reviewed snapshot with authenticated, revision-scoped graph and historian retrieval.
