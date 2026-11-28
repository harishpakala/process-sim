# SELiRA research artifact — RC01 candidate

This research extraction retains the scientific implementation from process-sim. The manuscript evaluation baseline is [commit `255f664de346a9f65d5cc11c3f180067d3551e16`](https://github.com/harishpakala/process-sim/tree/255f664de346a9f65d5cc11c3f180067d3551e16), which includes IC14. RC01 is a documentation/reproduction consolidation branch, **not a frozen release**. Do not equate the historical reports in `evaluation/results/archived` with current manuscript targets.

## Reproduce

Use Python 3.12.0 (recorded Windows 11 AMD64 experiments), or Python >=3.10 with deviations documented. From `selira_artifact`:

```sh
python -m venv .venv
# Activate .venv (Windows: .venv\\Scripts\\activate; POSIX: . .venv/bin/activate)
python -m pip install -e ".[test]"
python -m pip install -r evaluation/requirements-experiment.txt
python evaluation/reproduce_all.py
```

Do not use Python optimization flags (the runners assert experimental invariants). RC01 verifies a new execution, not merely the presence of committed JSON. It writes `evaluation/results/reproduced/verification_report.json` with input SHA-256 values and an installed-package environment inventory. Because transitive packages are not locked, independent reruns must capture their own `pip freeze`/environment inventory; the original experiment's complete dependency environment is not recoverable from the committed records.

## Current manuscript evaluation targets

| Evaluation | Target |
| --- | ---: |
| RQ1 semantic preservation, referential / identifier configurations | 81 / 40 (121 total) |
| RQ2 qualification/admission scenarios | 25 |
| RQ2 evidence-change cases / submissions / contract-level assertions | 6 / 18 / 72 |
| RQ3 graph-dependent snapshot comparisons | 1,808 |
| RQ3 evidence-qualified snapshot comparisons | 512 |
| Integrated focus instances (SC-01 / SC-02 / SC-03 / SC-04) | 38 / 39 / 40 / 71 (188 total) |
| Original violations (SC-01 / SC-02 / SC-03 / SC-04) | 0 / 9 / 29 / 0 (38 total) |
| Integrated lifecycle events (original dataset included) | 16 |
| Integrated full / selective logical evaluations | 2,444 / 203 |
| Integrated logical-evaluation reduction | 91.69% |
| Original integrated union graph | 30,611 triples |

These are expected counts to check on a fresh run, not evidence that this branch has passed. The IC14 evidence-qualified test performs 256 ordered comparisons for each of two coverage modes (512 total), with 1,024 full contract-level evaluations per mode; these must not be presented as 512 independent pytest cases. The RQ3 and integrated workload metrics are different populations and must not be pooled. Timing speedups are not claimed.

## Older archived results

The original README described 81 semantic configurations, 1,296 bounded SC-01 snapshot transitions, 182 integrated focus instances, and 11 historical integrated events (1,638 full / 195 selective logical evaluations). These are **preserved historical baselines**, not the current manuscript's targets. RC01's runner checks historical characterization and separate historical summary metadata without requiring the evolved integrated report to equal the historical archive byte for byte.

The earlier final benchmark records are separately documented in [evaluation/FINAL_EVALUATION.md](evaluation/FINAL_EVALUATION.md). Their timing results are separate workloads.

## Verification limits and release gates

Full SHACL validation remains part of admission; selective savings are logical contract-instance evaluations, not proven runtime speedups. Evidence attestations are externally supplied. No new SELiRA mechanism or SAFSL grammar change is part of RC01.

The original experimental environment records Python 3.12.0, Windows 11 AMD64, RDFLib 7.6.0, pySHACL 0.31.0 and Lark 1.3.1. CPU/RAM, GraphDB version, transitive dependencies and precise IC14 runtime environment are **not established**. See [evaluation/README.md](evaluation/README.md).

**Not ready for public artifact release:** confirm dataset provenance and redistribution permissions, upstream SAFSL rights, artifact-wide licensing, citation metadata, exact release environment, clean-environment reproduction, and final release/tag. Do not infer permission from public GitHub visibility. See [RC01_RELEASE_CHECKLIST.md](RC01_RELEASE_CHECKLIST.md).
