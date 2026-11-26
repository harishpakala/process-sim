# SELiRA research artifact

Standalone extraction of the paper-relevant implementation from process-sim baseline `20cb091239cc6cbf888100826416abbaeff79241`. The original integration remains unchanged. This is a staged research artifact, not an independent public release.

## Installation and verification

Use Python 3.10 or later in a clean virtual environment. From this directory:

```sh
python -m pip install -e ".[test]"
python evaluation/reproduce_all.py
```

The runner executes the regression suite, aggregates bounded SC-01 reassessment counts, and compares the dataset characterization, baseline and integrated experiment with archived results. Outputs are written to evaluation/results/reproduced. Run without Python optimization flags (assertions are required).

## Evaluation scope

- RQ1: 81 bounded graph configurations, compiler versus independent reference semantics.
- RQ2: admission regression tests; exact original nine-scenario experiment still to be located or reconstructed transparently.
- RQ3: 1296 bounded snapshot transitions and 80 Boolean policy configurations.
- Integrated: five RDF representations, four contracts, two policies, eleven submissions.

Logical reassessment counts are not runtime speedups. Full SHACL validation remains the admission gate; evidence attestations are caller-supplied. No independent evidence authentication or general incremental SHACL implementation is claimed.

## Reproducibility status

The extracted 121-test suite and integrated summary were reported reproduced locally. The consolidated runner still requires execution. Archived environment: Python 3.12.0, RDFLib 7.6.0, pySHACL 0.31.0; complete dependency locking is pending a clean environment inventory. The runner records actual input hashes including policies, but historical policy hashes are unavailable.

Upstream SAFSL provenance is retained in selira/language/PORTING.md and selira/language/__init__.py. Dataset redistribution rights, artifact-wide licensing and citation metadata require confirmation before release.
