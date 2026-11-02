# E11–E20 exploratory challenge protocol

## Status and preconditions

This is an **exploratory development benchmark**, not a held-out
independent validation set. Its design follows inspection of the
E1–E10 implementation and published expected outcomes. No independent
reviewers, authenticated plant evidence, or independently adjudicated
reference labels are available. Never report these outputs as accuracy.

E1–E10 and their internal validation should remain frozen for
historical comparison. E11–E20 input perturbations are recorded in
`scripts/run_selira_e11_e20_challenge.py`. Unexpected decisions are
preserved in JSON, not overwritten with target labels.

## Challenge inventory

| ID | Evidence perturbation | Status |
|---|---|---|
| E11 | Append contradictory identity assertion | Executable |
| E12 | Remove provenance from one identity assertion | Executable |
| E13 | Append applicability assertion from old revision | Executable |
| E14 | Retain only two identity-chain assertions | Executable |
| E15 | Change operational pressure unit to bar | Executable |
| E16 | Explicitly contradict operational binding | Executable |
| E17 | Remove CAC-01 measurement coverage check | Executable |
| E18 | Mark CAC-02 approval check VIOLATED | Executable |
| E19 | Conflicting measurement time intervals | Unsupported schema |
| E20 | Evidence conflicts requiring authority precedence | Unsupported schema |

E11/E13 probe how the current evaluator handles mixed assertions;
they do not establish a normative conflict-resolution policy.
E15 tests recognition of a dimension-compatible unit, **not** numeric
conversion accuracy. E12 probes provenance checks only to the extent
implemented by the current evaluator. E19/E20 are recorded explicitly
as unsupported rather than faking a result.

## Run (PowerShell)

```powershell
git switch docs/readme-startup-simplification
git pull origin docs/readme-startup-simplification
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -p "test_selira_e11_e20_challenge.py" -v
python scripts/run_selira_e11_e20_challenge.py --output selira-e11-e20-results.json
```

The runner records the full synthetic input assertions and contract
outcomes for each executable scenario, with no expected reference label.
All engineering authorizations remain false.

## Next experimental gates

1. Inspect unexpected outcomes and document whether the issue is a
   specification ambiguity, unsupported feature, or implementation bug.
2. Define E19/E20 evidence schemas and rules before implementing them.
3. Add a common RDF encoder for E11–E20 before claiming a comparison
   against semantic/task-aware SHACL. The current SHACL graph builder
   supports E1–E10 only; reusing it unchanged would be invalid.
4. Obtain independent adjudication on a **new frozen dataset** after
   any rule tuning. Do not count development cases as untouched holdout.
5. Report limitations and negative findings without suppressing them.

The experimental contract catalog is `selira.experimental.v0.1`;
README-proposed SC numbering remains unreconciled.
