# Final TEP NEXUS evaluation (EV-06 / EV-11)

Archive the original user-produced JSON reports without editing them in
`evaluation/results/archived/final/`:
- controlled_tep_initial.json (30 paired lifecycle scenarios, one repetition)
- representative_tep.json (five independently baseline-seeded scenarios, three repetitions)

From selira_artifact, run `python evaluation/verify_final_results.py` for offline
record and checkout-hash checks. This does not reconstruct graph states or rerun SHACL.
The runners asserted graph-state preservation during execution.

Experimental source revisions: e563828 (comprehensive), 1c21594 (representative).
Recorded environment: Python 3.12.0, Windows 11 AMD64, RDFLib 7.6.0,
pySHACL 0.31.0, Lark 1.3.1. CPU/RAM and transitive dependency versions were not recorded.
Use `python -m pip install -e ".[test]"` then
`python -m pip install -r evaluation/requirements-experiment.txt`.
Run `python -m pytest tests -q` for regression verification.

Optional expensive reproduction (not required for offline verification):
```
python evaluation/benchmark_tep.py --repetitions 1 --warmups 0
python evaluation/benchmark_representative_tep.py --repetitions 3
```
Use --resume for an interrupted representative run with identical configuration.
Both runners use the original semantic/ontology2 inputs by default.

Comprehensive: 15 V, 9 F, 6 U; 4661 vs 1459 executions; 102 vs 49 SHACL calls.
Representative: 2730 vs 645 executions; 60 vs 27 SHACL calls.
Do not pool the workloads. Timings are machine-specific; baseline initialization
is excluded from representative timings. Three repetitions do not establish
general scalability. The full strategy uses the same targeted SHACL machinery
as selective execution, not a comparison against other incremental engines.
The cache is in-memory and evidence attestations are supplied by the caller.
Archive and regression verification must be confirmed before declaring the artifact frozen.
