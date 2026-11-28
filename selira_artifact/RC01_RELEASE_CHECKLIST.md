# RC01 — research artifact readiness and release evidence

Research baseline: `255f664de346a9f65d5cc11c3f180067d3551e16`.
RC01 branch status: candidate only; never describe as a verified public release without recording the evidence below.

| ID | Task | Status at RC01 preparation | Evidence required before closure |
| --- | --- | --- | --- |
| RC01-A | Research README alignment | Implemented in proposed branch | Review manuscript numbers and distinctions |
| RC01-B | Evaluation README alignment | Implemented in proposed branch | Review target/archived split |
| RC01-C | Current reproduction runner | Implemented in proposed branch; not freshly executed | Clean run of `python evaluation/reproduce_all.py` |
| RC01-D | Complete experimental environment | Partial capture on future run | `pip freeze --all`, OS/architecture, Python, hardware, GraphDB if applicable; identify deviations from older records |
| RC01-E | IC14 in reproduction report | Explicit module execution configured; unexecuted | Passing test outputs and 18-submission/512-comparison provenance |
| RC01-F | Expected results and SHA-256 | Expected integrated assertions and current input hashing configured | Review report values and input hash ledger from clean checkout |
| RC01-G | Artifact license and dataset rights | BLOCKED: not verified | Written assessment of each dataset, ontology, binding, third-party component, and upstream SAFSL code; attach licenses/permissions |
| RC01-H | Freeze final research artifact | BLOCKED | All above resolved, code review, reproducible clean run, immutable tagged commit/release with checksum |

## Reviewer sign-off and cautions

- Scientific implementation, SAFSL grammar, datasets, archived JSON, and IC14 test bodies are unchanged by RC01.
- Existing public GitHub access is **not** proof of dataset redistribution permission or a project license.
- Do not publish a release or merge to main until the unverified gates are resolved.
- Current integrated targets: 188 instances, 16 lifecycle events, 2,444 full vs 203 selective logical evaluations, 13 equivalent comparisons, 30,611 triples; separate IC14 targets: 18 evidence-change submissions and 512 evidence-qualified comparisons.
- Historical records remain available independently of the current manuscript baseline.
- Record the responsible reviewer, verification date, checkout commit, command transcript, package inventory and any deviations in the release evidence before checking RC01-H.
