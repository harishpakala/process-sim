# SELiRA — Formal Contract Composition (Draft v0.1)

**Status:** Proposed formal specification; not an implemented or empirically validated guarantee.  
**Scope:** Aggregating engineering semantic contract results for a correspondence at a consistent revision.  
**Out of scope:** Deriving engineering rules, automatic proof of source authority, or replacing contract-level SHACL execution.

## 1. Motivation and design constraints

A proposed correspondence is not valid merely because two RDF nodes can be linked. SELiRA evaluates explicit, approved engineering requirements with revision-bound evidence. Composition must not (a) silently promote missing evidence to validity, (b) count an inapplicable contract as a success, (c) hide an established violation behind an indeterminate result, or (d) treat an unexecuted mandatory contract as a pass.

The existing six contract families are SC-01 identity/reference integrity, SC-02 physical-quantity compatibility, SC-03 units, SC-04 engineering constraints, SC-05 cross-representation relationships, and SC-06 evidence/revision traceability. This specification **does not assert that every family applies to every correspondence**. Their engineering rules and applicability must be separately approved.

## 2. Formal universe and revision context

Let:
- `K` be the set of candidate correspondences, each with a stable identifier.
- `C` be the set of versioned semantic contracts.
- `r = (r_G, r_C, r_A)` be a **consistent revision context**: source graph revision vector, contract-set revision, and approved-requirements/authority revision.
- `G_r` be the evidence graph associated with `r_G`.
- `A_r` be approved engineering requirements and authority assignments associated with `r_A`.

Define the evaluation context `x = (k, r)`, with `k ∈ K`. All results composed for `x` MUST refer to the same revision context; otherwise the composition is **not evaluable** and must not be published as current validity.

Each contract has a declared applicability predicate `Applies(c,x) ∈ {true,false,unknown}`, a role `Role(c,x) ∈ {mandatory,advisory}` when applicable, and a contract evaluation outcome.

The four contract outcomes are:

`O = {V, F, U, NA}`

- `V` (VALIDATED): an applicable contract is satisfied using sufficient authoritative evidence.
- `F` (INVALID): an applicable contract is violated, with sufficient authoritative evidence to establish the violation.
- `U` (INDETERMINATE): applicability or required evidence/evaluation cannot be conclusively established.
- `NA` (NOT_APPLICABLE): contract is established to be outside the correspondence scope.

**Rule:** `NA` requires proven non-applicability; missing data is not evidence of non-applicability. `PENDING_REVALIDATION` is a separate lifecycle state, not an outcome in `O`.

## 3. Contract registry and coverage

For `x`, a versioned **required-contract registry** `Req(x)` lists all mandatory contract instances that policy requires evaluating. `Adv(x)` lists advisory instances. Both are determined by approved policy, not by whichever results happen to be present. Each instance is uniquely keyed by correspondence, contract identifier, contract version, and revision context.

`CoverageComplete(x)` holds only if:
1. The applicable contract registry and policy revision are known and approved.
2. Each required contract instance is accounted for exactly once with a compatible revision context.
3. Applicability has been resolved for each required instance, or explicitly recorded as unknown.
4. The registry is closed for this evaluation (no unexamined required contract classes).

An absent evaluation for a required instance is represented as `U` in aggregation; it must **never** be interpreted as `NA` or `V`. Unknown applicability is likewise `U`.

A contract that is conclusively inapplicable is `NA` and excluded from mandatory conjunction. A correspondence with no applicable mandatory contracts must not be certified as `V` merely because the conjunction is empty.

If the registry itself is missing, unapproved, or of unknown completeness, the aggregate is `U` regardless of any observed passing results; a proven violation may still be reported at contract level, but **aggregate `F` requires a trustworthy mandatory scope and an established applicable violation**.

## 4. Conjunctive mandatory composition

For a **known, approved registry**, normalize each required instance to `V`, `F`, `U`, or `NA` using Section 2. Let `M_x` be the multiset of normalized required outcomes and `E_x` be `M_x` after removing `NA`.

Define `ComposeMandatory(M_x)`:

1. If any member of `E_x` is `F`, return `F`.
2. Else if any member of `E_x` is `U`, return `U`.
3. Else if `E_x` is empty, return `NA`.
4. Else (every member of `E_x` is `V`), return `V`.

If the registry is not trustworthy/complete, return `U` instead of calling `ComposeMandatory`.

The operator is defined on normalized mandatory outcomes, not raw SHACL conformances. It is a policy for **conjunctive mandatory requirements**; alternative policies must be explicit, separately versioned, and independently justified.

### 4.1 Binary truth table (nonempty pairwise fold)

The binary operator `⊗` below is used for folding outcomes. `NA` is an identity for an already established applicable result; `NA ⊗ NA = NA`.

| ⊗ | V | F | U | NA |
|---|---|---|---|---|
| **V** | V | F | U | V |
| **F** | F | F | F | F |
| **U** | U | F | U | U |
| **NA** | V | F | U | NA |

A fold over an empty set returns `NA` by explicit definition. **The binary table alone does not enforce registry completeness, role assignment, or evidence sufficiency.**

### 4.2 Advisory contracts

Advisory contract outcomes are recorded and reported separately. They do **not** change the mandatory aggregate unless an approved policy explicitly promotes a particular advisory requirement to mandatory for that correspondence and revision. Advisory violations must remain visible and auditable; they cannot be silently discarded.

### 4.3 Aggregated publication gate

Define `PublishableAsValidated(x)` iff all hold:
- Registry, roles, authority, and revision context are approved and complete.
- Mandatory aggregation yields `V`.
- At least one mandatory contract is established applicable and evaluated.
- No required evaluation is missing, stale, or pending revalidation.
- Validation provenance meets the declared audit policy.

The lifecycle layer may mark `x` as `PENDING_REVALIDATION`; then no historical `V` may be advertised as **current certification**, even though the historical record remains immutable.

## 5. Examples (illustrative, not claims about actual engineering assets)

| Example | Required outcomes | Advisory outcomes | Mandatory aggregate | Notes |
|---|---|---|---|---|
| A | SC-01 V, SC-02 V, SC-03 V | — | V | Only if registry complete and other publication conditions hold |
| B | SC-01 V, SC-04 F | — | F | Proven applicable mandatory violation |
| C | SC-01 V, SC-04 U | — | U | Configured engineering range unavailable |
| D | SC-01 NA, SC-04 NA | — | NA | No mandatory contract applies; no vacuous acceptance |
| E | SC-01 V, SC-03 missing | — | U | Required evaluation not executed |
| F | SC-01 V | SC-04 F | V | Advisory warning separately visible; no mandatory failure |
| G | SC-01 V, SC-04 F | — | U | **Registry not approved/complete**: aggregate withheld; SC-04 violation still reported |
| H | SC-01 V, SC-03 NA | — | V | Valid only when SC-03 non-applicability is established and mandatory coverage complete |

Example B is not a claim that any current product or instrument is unsuitable. Engineering violations must be supported by actual approved requirements and configuration evidence.

## 6. Proposed formal properties

For a known complete registry and normalized outcomes:

- **Commutativity:** `a ⊗ b = b ⊗ a`.
- **Associativity:** `(a ⊗ b) ⊗ c = a ⊗ (b ⊗ c)`.
- **Idempotence:** `a ⊗ a = a`.
- **Identity:** `a ⊗ NA = a`.
- **Established violation dominance:** `a ⊗ F = F`.
- **No vacuous success:** `ComposeMandatory([]) = NA`.
- **Missing mandatory evidence:** if no `F` exists and any required outcome is `U`, aggregate is `U`.
- **Revision isolation:** results from incompatible revision contexts cannot be composed into a current outcome.

The first five are algebraic properties of the proposed table, suitable for exhaustive tests over the four-element domain. The final two require registry and revision-aware implementation tests. A mathematical proof and verified implementation have **not yet been supplied**.

## 7. Relationship to lifecycle and provenance

For each `(k,c,r)`, persist an individual evaluation record and supporting evidence. For each `(k,r)`, persist a composition record referencing the exact constituent evaluation record IDs, registry/policy version, aggregate outcome, and timestamp. When a relevant source, contract, authority, or registry revision changes, the affected pair or aggregate becomes `PENDING_REVALIDATION`. A new current record must not overwrite historical records.

An aggregate must be recomputed when: (i) a required outcome changes, (ii) contract applicability changes, (iii) role/required registry changes, (iv) evidence sufficiency or authority changes, or (v) the revision context changes in a relevant way.

## 8. Implementation contract and acceptance tests (planned)

Suggested pure function interface:

```python
compose_mandatory(
    required_contract_ids: set[str],
    evaluations: dict[str, ContractEvaluation],
    registry_approved: bool,
    registry_complete: bool,
    revision_context: RevisionContext,
) -> CompositionResult
```

The implementation must reject duplicate/conflicting evaluation records, detect mismatched revisions, represent absent required results as `U`, and return a reason code and constituent evidence references. `CompositionResult` should distinguish aggregate **outcome** from lifecycle **state** and `publishable_as_validated`.

Minimum test set:
1. Exhaustively check the 16 binary table cells.
2. Check commutativity, associativity (64 triples), idempotence, and identity.
3. Verify permutations of mandatory evaluations yield the same aggregate.
4. Verify missing required result => U unless a proven F dominates within a complete registry.
5. Verify missing/unapproved registry => U even with a proven contract-level F.
6. Verify all NA / no applicable mandatory contracts => NA.
7. Verify unknown applicability => U.
8. Verify advisory F does not change mandatory aggregate but is reported.
9. Verify stale/mismatched revisions cannot produce current V.
10. Verify PENDING_REVALIDATION prevents current certification.
11. Verify provenance references all evaluated and required-but-missing contract instances.
12. Verify changes to registry/applicability/authority trigger re-composition.

## 9. Open design decisions requiring engineering review

1. What approved rule determines which SC-01–SC-06 contracts are mandatory for each correspondence type?
2. What evidence establishes that the required-contract registry is complete?
3. Should a known mandatory violation yield aggregate F if registry completeness is unknown? **Draft policy: no; report F at contract level, aggregate U.**
4. How should advisory outcomes be exposed to downstream consumers?
5. What is the authoritative revision vector for concurrent updates across GraphDB named graphs and contract/authority registries?
6. Is a dedicated `BLOCKED` operational status needed for evaluation failures? **Do not add a fifth contract outcome without formal review.**
7. How should contradictory authoritative evidence be represented? **Draft policy: U pending conflict resolution, unless an approved conflict rule establishes a conclusive result.**

## 10. Next steps

1. Review and approve the semantics above with engineering stakeholders.
2. Implement a pure composition module and exhaustive unit tests.
3. Bind actual SC-01–SC-06 evaluations to revision-aware contract instances.
4. Integrate with lifecycle invalidation and persistent RDF provenance.
5. Demonstrate engineering cases and compare against independently reviewed ground truth.

**Research caution:** The four-valued outcome model and aggregation policy are proposed SELiRA semantics. Novelty over existing multi-valued logics, policy engines, contract systems, and incremental constraint validation requires a related-work analysis.
