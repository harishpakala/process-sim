# SELiRA evaluation — manuscript baseline and reproduction

**Immutable scientific baseline:** `255f664de346a9f65d5cc11c3f180067d3551e16` (IC14 integrated). RC01 changes documentation and the verification harness only.

## One-command functional reproduction

From `selira_artifact`, after `python -m pip install -e ".[test]"` and `python -m pip install -r evaluation/requirements-experiment.txt`:

```sh
python evaluation/reproduce_all.py
```

The runner calls the full pytest regression suite, explicitly invokes both IC14 test modules, checks the historical bounded SC-01 workload, reruns dataset characterization and the four-contract baseline/lifecycle, verifies current integrated targets, and writes `results/reproduced/verification_report.json`. It stops on the first failing subprocess or assertion. Its report contains the installed distribution versions, platform, Python executable, and SHA-256 of dataset/contract/binding/policy files. Run without `-O`.

### Expected current-manuscript results

| Workload | Expected | How checked |
| --- | --- | --- |
| RQ1 referential and identifier configurations | 81 + 40 = 121 | Regression suite and four-contract violation sets |
| RQ2 systematic qualification/admission | 24 + 1 = 25 scenarios | Regression suite |
| IC14 evidence-only qualification | 6 cases, 18 submissions, 72 contract-level assertions | `tests/test_ic14_evidence_changes.py` |
| RQ3 graph-dependent snapshot comparisons | 1,808 | Regression suite (prior experimental assertions) |
| IC14 evidence-qualified comparisons | 256 covered + 256 fallback = 512 | `tests/test_ic14_qualified_reassessment.py` |
| IC14 full evaluations | 1,024 per coverage mode | Same test; not an integrated count |
| Integrated focus population / original violations | 188 / 38 | Rerun `multi_contract_baseline.py` |
| Integrated original union triples | 30,611 | Rerun `multi_contract_lifecycle.py` |
| Integrated lifecycle events (includes original baseline) | 16 | Rerun `multi_contract_lifecycle.py` |
| Integrated decisions | 7 admitted, 8 rejected, 1 deferred | Same |
| Integrated logical evaluations | 2,444 full / 203 selective | Same |
| Integrated preservation comparisons | 13 equivalent of 13 | Same |

The script reports some RQ1/RQ2/RQ3 systematic counts as test-covered targets, rather than independently extracting every comparison counter from machine-readable pytest output. Consequently, a successful report validates test execution and explicit integrated assertions, but should not be misread as a newly constructed per-scenario ledger.

### Historical (not current) targets

`results/archived/multi_contract_baseline.json` and `results/archived/multi_contract_lifecycle.json` preserve a prior run: 182 focus instances, 25,502 union triples, 11 events, 1,638 full vs 195 selective logical evaluations, 9 equivalence checks, and 1,296 bounded SC-01 transitions. These are intentionally *not* compared byte-for-byte with the current 188-instance report. The current report has different contracts/bindings, graph scope, and workload. Historical files must remain unchanged.

### Provenance, environment, and optional benchmarks

Source of current integrated expected values: `results/reproduced/multi_contract_lifecycle.json`; source for violation populations: `results/reproduced/multi_contract_baseline.json`. On any fresh run, validate hashes against that run's report. Paths in older JSON records may use Windows backslashes, so hash comparison normalizes the filename only when matching recorded historical inputs.

The older experimental environment was Windows 11 AMD64 / Python 3.12.0 / RDFLib 7.6.0 / pySHACL 0.31.0 / Lark 1.3.1. Experimental dependency requirements pin the three named libraries; `pyproject.toml` requires Python >=3.10 and declares version 0.1.0.dev0. The IC14 run's exact environment, GraphDB version, CPU/RAM, transitive package versions, and install/build metadata were not archived. Capture `python -m pip freeze --all` and `python -m pip debug --verbose` when collecting release evidence. A `pip freeze` from a *new* environment must not be represented as the original environment.

Run `python evaluation/verify_final_results.py` separately for **offline** verification of the earlier benchmark archives: it does not rerun SHACL. Full benchmark reruns are documented in `FINAL_EVALUATION.md`, and their runtime results must not be conflated with logical evaluation savings.

### Release condition

RC01 does not authenticate evidence, validate external data ownership, or certify permission to redistribute TEP NEXUS/AAS inputs. Licensing and redistribution review, complete environment capture, and an independent clean-environment rerun are still required before a final release.
