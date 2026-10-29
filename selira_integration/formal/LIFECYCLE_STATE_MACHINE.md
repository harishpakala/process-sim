# F6 — Revision-aware lifecycle state machine (draft v0.1)

**Status:** Executable reference model, not an empirical correctness guarantee.

## Scope and separation

A semantic-contract **outcome** belongs to `{VALIDATED, INVALID, INDETERMINATE, NOT_APPLICABLE}`. A lifecycle **phase** belongs to `{UNVALIDATED, CURRENT, PENDING_REVALIDATION}`. They are orthogonal. In particular, a previously VALIDATED result in a PENDING state is *historical*, not a certification of the target revision.

A state is `s=(correspondence_id, phase, target_revision, current_record?, history)`. A validation record is `(revision, outcome, provenance_attested)`. Revision is the complete graph/contract/authority vector from F3. History is append-only and includes superseded records. A target revision can change again while pending; no prior evaluation becomes current by default.

## Transition relation

1. **create(k,r)**: initialize `UNVALIDATED` for target `r`, no record.
2. **change(s,r')**: when `r' != target_revision`, transition to `PENDING_REVALIDATION` and set the target to `r'`. The previous current record is retained only in history. Repeated changes during pending update the target.
3. **validation_complete(s, result)**: allowed only when the result corresponds to the state's target revision and correspondence; result must come from the approved composition interface. Append its record and transition to `CURRENT`. A composed INDETERMINATE outcome is a valid reportable result, not an incomplete lifecycle transition.
4. **invalidate_current(s)**: if change impact is not yet resolved, conservatively mark pending at the existing target; no current certification may be exposed until a consistent revalidation decision.
5. A no-op change with an identical target revision does not change the state.

## Safety invariants

- **I1 No stale certification:** `CURRENT` implies the stored current record has the target revision. `PENDING` and `UNVALIDATED` never expose a current record.
- **I2 Revision consistency:** the accepted composition result must use the same correspondence and full revision vector.
- **I3 No premature promotion:** `publishable_as_validated` requires CURRENT phase, VALIDATED outcome, approved complete registry, and attested provenance (as enforced by F3).
- **I4 Append-only history:** transition never deletes previous records.
- **I5 Conservative invalidation:** unknown impact requires pending; a sound F5 impact analysis is a prerequisite for leaving unaffected results CURRENT.
- **I6 No invented results:** a lifecycle transition cannot turn INDETERMINATE into VALIDATED; F3 remains responsible for outcome calculation.

## Relationship to F5 and F7

F5 identifies affected contract instances; F6 marks affected correspondences pending. F7 must show that reused contract evaluations remain semantically equivalent to a fresh evaluation at the new revision. The state machine alone cannot establish this property.

## Limitations

This reference module uses immutable in-memory state. Persistence, atomic publication, concurrent revision handling, GraphDB integration, and authoritative evidence verification are **not implemented**. The transition model requires a caller to perform dependency soundness checks; it must not infer them from a missing dependency list.
