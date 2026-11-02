# SELiRA formal semantics — draft v0.1 (CAiSE 2027)

**Status:** research specification, not a certification standard. This document
formalizes the *implemented* experimental evaluators and marks proposals
separately. Existing benchmark output remains unchanged.

## 1. Domains and scope

Let `e` be an evidence snapshot, `t` a consumer task, and `r` the
declared engineering configuration/revision scope. Source qualification
comprises five implemented experimental checks:

- SC-01: cross-domain identity chain (DEXPI→ECAD→PLC→OPCUA→TEP).
- SC-02: engineering/operational quantity-kind compatibility.
- SC-03: engineering/operational measurement-unit dimensional compatibility.
- SC-04: task configuration and revision applicability.
- SC-05: operational endpoint binding assertion.

The two implemented consumer checks are CAC-01 (operational evidence fitness)
and CAC-02 (engineering restriction fitness).

An evidence assertion may include a claim, `evidenceRef`, provenance source,
revision/configuration, and an `authority` marker. **The prototype checks
the presence and equality of these fields; it does not cryptographically
authenticate them or independently verify a source.** In particular,
`authority="AUTHENTICATED"` in a synthetic fixture is a test input, not
an attestation.

## 2. Verdicts

Let `S={V,F,U}` for source contracts: V means evaluator-level verification
under supplied assertions; F means an eligible contradiction or violation;
U means insufficient or inapplicable-to-the-evaluator evidence without a
supported contradiction.

Let `C={V,F,U,NA}` for consumer fitness. NA means **explicitly out of
scope** for a particular consumer task. NA is not verification.

For a finite, nonempty sequence `x` of source verdicts, define

```text
AND3(x) = F   if F is present
          V   if every element is V
          U   otherwise
```

The implemented `conjunction` also yields U on an empty sequence or any
invalid value. Define source qualification `QS(e)=AND3(SC_i(e))`.

For each consumer task contract `j`, define `FC_j(e,t)∈C`. Integrated
task decision `D_j(e,t)=JOIN(QS(e),FC_j(e,t))` is:

| Source QS | Fitness V | Fitness F | Fitness U | Fitness NA |
|---|---|---|---|---|
| V | V | F | U | NA |
| F | F | F | F | NA |
| U | U | F | U | NA |

**NA precedence:** this is the current implementation: explicit out-of-scope
fitness returns NA even if source qualification is F. NA means the task is not
evaluated; it does **not** erase or change the separately reported source F.

The prototype *always* returns `authorization=false`,
`accepted=false`, and `engineeringCertification="U"`. These flags are
not derived from `D=V`; production authorization is outside this model.

## 3. Evidence eligibility and decision boundaries

SC-01 requires four exact identity correspondences for the declared revision,
with eligible provenance and authority markers. An eligible contradiction
dominates verified links; missing links yield U.

SC-02 requires engineering and operational quantity-kind assertions at the
declared revision. Conflicting eligible kinds yield F; missing sides yield U.
SC-03 similarly requires supported dimensional units; incompatible dimensions
yield F, unknown units yield U. Unit compatibility does not establish quantity
identity or correct sensor scaling in situ.

SC-04 requires exact task configuration and revision. Eligible INAPPLICABLE
dominates; an assertion for another revision is not evidence of a violation
for this revision and yields U.

SC-05 requires a matching signal, NodeId and revision with an eligible BOUND
or CONTRADICTED assertion. A declared RDF mapping or populated NodeId alone
does not establish a live OPC UA binding.

CAC-01 checks `runId,timeInterval,units,provenance,measurementCoverage`;
CAC-02 checks `approval,targetProperty,units,configuration`. Each
requirement is checked against caller-supplied eligible MET/VIOLATED
assertions; any eligible violation yields F, all MET yields V, otherwise U.
A missing approval check is U, not F. No historian measurement coverage or
actual engineering approval is independently verified by these evaluators.

## 4. Versioned catalog and backward compatibility

**Catalog identifier:** `selira.experimental.v0.1`. It is a versioned
*description* of current code, **not** a completed reconciliation of the
README proposal.

| Experimental ID | Implemented check | Python implementation |
|---|---|---|
| SC-01 | Identity chain | `sc01_contract.evaluate_sc01` |
| SC-02 | Quantity kind | `sc02_contract.evaluate_sc02` |
| SC-03 | Measurement units | `sc03_contract.evaluate_sc03` |
| SC-04 | Configuration/revision | `sc04_contract.evaluate_sc04` |
| SC-05 | Operational binding | `sc05_contract.evaluate_sc05` |
| CAC-01 | Operational evidence fitness | `cac_contracts.evaluate_cac` |
| CAC-02 | Engineering restriction fitness | `cac_contracts.evaluate_cac` |

The README-proposed SC-02 is the broader **engineering-to-signal meaning
consistency** contract and SC-03 is **configuration/revision applicability**.
These names do not correspond one-to-one to experimental SC-02/SC-03.
A future canonical `selira.contracts.v1` must explicitly decide whether
meaning consistency composes quantity kind and unit compatibility, and must
publish a migration mapping. **Do not reinterpret historical SC-02/SC-03
results as the README contracts.** See `docs/research/selira/selira-contract-alignment.md`.

## 5. Properties testable against the implementation

P1 (failure dominance): if any valid SC verdict is F, QS=F.
P2 (unknown preservation): if no SC is F and at least one is U, QS=U.
P3 (source gate): for fitness V, D=V iff QS=V; QS=F→D=F and QS=U→D=U.
P4 (consumer violation): for in-scope fitness F, D=F regardless of QS.
P5 (task non-applicability): fitness NA→D=NA; authorization remains false.
P6 (fail-closed flags): for all valid synthetic verdict combinations,
authorization=false, accepted=false, engineeringCertification=U.

These are **implementation invariants**, not proofs of source authenticity,
field safety, or universal correctness. Tests enumerate the finite verdict
space; external authorization remains unimplemented.

## 6. Empirical status and threats to validity

E1–E9 mutate synthetic evidence *before* evaluating contracts. E10 uses
focused GraphDB relationship discovery for XMEAS7 and remains U. Synthetic
reference labels are predefined scenario expectations, not independent
adjudication. B1/B2 are naive presence comparators, not real SHACL
implementations. No live OPC UA verification, approved restrictions,
independently authenticated source authority, or generalizable performance
study has been demonstrated.

Next research milestones: review canonical catalog mapping, define an
independent evidence-attestation model, run an actual SHACL comparator on
equivalent RDF input, adjudicate labels independently, and benchmark runtime.
