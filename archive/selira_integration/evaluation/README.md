# SELiRA SC-01 engineering evaluation

This reproducibility package supplements the bounded synthetic experiments with successive candidate submissions over existing TEP NEXUS engineering RDF. It is a local reference implementation, not a production deployment.

## Inputs and revisions

Run from the repository root in an environment with process_sim and its dependencies installed (including RDFLib, pySHACL, Lark and pytest). Reported environment: Windows, Python 3.12.0, pytest 9.1.1. Exact dependency versions beyond those reported were not captured.

- RDF: semantic/ontology2/assetinventory-instance.ttl and productcatalog-instance.ttl.
- Contract: selira_integration/contracts/safsl/SC-01.safsl.
- Bindings: selira_integration/contracts/bindings/SC-01.json.
- Orchestrator: src/process_sim/selira/automation_manager.py.
- Lifecycle experiment source revision: d43fb7cd3d2c58cb88b0d236a829f0a8a175590c.
- Focused regression source revision: aa3e8e0f116769aeb0836008bba3654ce7d09a86.

The revisions identify the committed sources preceding the reported runs; local HEAD and working-tree cleanliness were not independently recorded. The later archive commits do not alter those sources.

## Reproduction

From the repository root:

```powershell
python selira_integration/evaluation/characterize_dataset.py
python -m process_sim.safsl.shacl.compiler selira_integration/contracts/safsl/SC-01.safsl selira_integration/contracts/bindings/SC-01.json selira_integration/contracts/generated/SC-01
python -m selira_integration.evaluation.sc01_lifecycle
python -m pytest tests/test_safsl_shacl_sc01.py tests/test_safsl_semantics_differential.py tests/test_safsl_admission.py tests/test_safsl_lifted_admission.py tests/test_safsl_sqlite_admission.py tests/selira/test_selira_f7_selective_equivalence.py tests/selira/test_automation_manager.py -q
```

The lifecycle script recompiles the contract internally, uses a fresh in-memory store, and asserts verdicts, commit decisions, version progression, graph preservation and reference outcome equivalence. It does not modify the source RDF files. Archive fresh outputs separately from the recorded results.

## Observations

The baseline contains 7,042 RDF triples, 43 assets and 20 products. All 38 assigned assets have exactly one matching product; five unassigned assets are outside the predicate-targeted scope. Generated SHACL conformed in the reported baseline run, with zero non-asset focus nodes.

| Event | Verdict | Version after | Full reference | Selective reference |
| --- | --- | ---: | ---: | ---: |
| E0 initial admission | V | 1 | — | — |
| E1 unreferenced catalog change | V | 2 | 38 | 0 |
| E2 valid reassignment | V | 3 | 38 | 2 |
| E3 unresolved assignment | F | 3 | 38 | 2 |
| E4 duplicate IFM | F | 3 | 38 | 5 |
| E5 duplicate SAMSON | F | 3 | 38 | 11 |
| E6 incomplete candidate evidence | U | 3 | 38 | 38 |
| E7 unconfirmed dependency coverage | V | 4 | 38 | 38 |

All eight decisions matched expectations; all seven reference comparisons agreed. The reference workload was 96 rather than 266 logical instance evaluations (170 fewer; 63.91% reduction). E2/E3 conservatively invalidate shared lookup scopes. E6 invalidates all instances through evidence dependency; E7 forces full fallback. E6/E7 are evidence-only submissions; E7 advances the local version without RDF changes. The focused regression suite reported 43 passes.

## Refactoring verification

The combined SELiRA and SAFSL run following reassessment relocation reported 278 passed, 329 subtests passed in 13.09 s, with all eight lifecycle decisions and seven reference comparisons preserved (266 full, 96 selective logical evaluations). The preceding committed source was `49ac28746b4b84539c42706f3f87964e74405bd9`. Local HEAD and working-tree cleanliness were not independently captured. After correspondence relocation (`3e787461bce6ca3856119185184f73b4382faa3b`), the operator reported a pass without detailed counts or lifecycle output; the subsequent archival verification reported 278 passed and 329 subtests passed in 12.98 s, and the E7 excerpt confirmed full fallback and equivalence. See [post-archival verification](results/post_archival_verification.txt). Complete post-archival lifecycle output and local revision/environment metadata remain unavailable.

To capture a fresh baseline in PowerShell:

```powershell
git rev-parse HEAD
git status --short
python --version
python -m pytest --version
python -m pytest tests/selira (Get-ChildItem tests/test_safsl*.py).FullName -q
python -m selira_integration.evaluation.sc01_lifecycle
```

Keep fresh logs separate from the original archived results.

## Archived results

- [Dataset characterization](results/dataset_characterization.json)
- [Lifecycle results](results/sc01_lifecycle_results.json)
- [Regression results](results/regression_results.txt)

JSON files preserve the uploaded observed data with normalized formatting. Regression results are transcribed from the reported terminal output.

## Scope and limitations

Completeness, canonical identity, applicability, dependency coverage and unchanged policy/authority are experimental caller attestations, not independent engineering approvals. The manager assumes single nonempty lexical identifiers per projected resource and checks assigned focus nodes against the asset class. Full compiled SHACL remains the admission gate when evidence and scope permit validation. The reference comparison computes both full and selective outcomes and prior outcomes; its counts are logical reassessment counts, not total operations, runtime savings or incremental SHACL performance. The store and audit history are local and in memory. The dataset is benchmark-derived and the candidate changes are controlled experimental perturbations, not observed plant changes. The historical 43-test focused run is distinct from the subsequent 278-test combined run; neither represents the entire repository suite.

## Current multi-contract experiment

The SC-01 results above are historical. The current experiment uses SC-01 through SC-04 and parsed LP-03/LP-04 decisions. See [reported verification](results/multi_contract_reported_verification.txt). The operator reported 365 tests and 329 subtests passing, and nine of nine selective/full comparisons agreeing. The logical workload was 195 versus 1,638 (88.10% reduction). The generated detailed JSON outputs and local revision metadata remain to be archived. Reproduce using the commands in the [current README](../README.md).
