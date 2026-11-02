# Blind engineering adjudication protocol

## Goal and limits

Collect reference decisions from independent engineering reviewers for
E1–E10 on three tasks: SOURCE, CAC-01 and CAC-02. **No reference labels
are provided by this repository.** Existing benchmark expectations are
developer-authored and must not be called independent ground truth.

## Reviewer materials

For E1–E9, export the underlying synthetic input assertion records from
`synthetic_case(case_id)` in
`scripts/run_selira_e1_e10_benchmark.py`. Include the task requirements,
the evidence assertions, revision and configuration, and provenance.
For E10, supply the unmodified focused GraphDB discovery report, its
query scope and truncation status, and the task requirements. Clearly
label synthetic records as synthetic and distinguish discovery triples
from authenticated assertions.

**Blindness:** reviewers must not see SELiRA decisions, SHACL conformance,
developer reference labels, or previous adjudications before submitting.

## Labeling instructions

Each reviewer labels each task as:

- **V**: all necessary task-scoped evidence is present, authentic,
  applicable, and consistent within the explicitly supplied scenario.
  For synthetic cases, V means *fixture-level* verification only.
- **F**: admissible evidence explicitly contradicts a mandatory contract
  or consumer requirement.
- **U**: necessary evidence is missing, insufficiently authenticated,
  out of revision, or inconclusive; no demonstrated contradiction.
- **NA**: consumer task explicitly out of scope; permitted only for
  CAC-01/CAC-02, never SOURCE.

For CAC tasks, reviewers should separately consider the source evidence
and consumer requirements, recording their evidence basis. If source
is F, the integrated consumer outcome follows the declared decision
policy; if source is U, the reviewer must not infer V merely from
consumer check presence. Reviewers must distinguish evidence validity
from engineering authorization: **authorization is always false**.

## Procedure

1. Freeze scenario dossiers and record SHA-256 hashes before labeling.
2. Recruit at least two reviewers who did not implement the evaluator.
3. Assign stable anonymous reviewer IDs. Review each SOURCE/CAC task
   independently using `selira-blind-review-template.csv`.
4. Require a specific evidence basis and rationale for each decision.
5. Calculate exact agreement and a confusion matrix for V/F/U/NA.
   Record disagreements and a third-party adjudication rationale.
6. Only after adjudication, compare labels against SELiRA and SHACL.
   Do not retroactively edit rules or shapes without a separate holdout.
7. Report reviewer qualifications, independence, conflict-of-interest,
   review duration, adjudication rates, and dataset limitations.

## Reproduce task-aware SHACL and generate empty review sheet

```powershell
git switch docs/readme-startup-simplification
git pull origin docs/readme-startup-simplification
$env:PYTHONPATH = "src"
python scripts/run_selira_task_aware_comparison.py `
  --focused selira-xmeas7-focused.json `
  --output selira-task-aware-shacl-results.json `
  --review-template selira-blind-review-template.csv
```

Task-aware SHACL uses separate CAC-01 and CAC-02 shapes, with required
check names and explicit violated-check detection. It does not implement
all authority, revision, unit conversion, or cross-contract rules.
SHACL binary conformance must not be reinterpreted as V/F/U.

Do not claim statistical significance, independently validated ground
truth, or real plant certification from these synthetic fixtures.
