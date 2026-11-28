# MODELSWARD 2027 comparative evaluation protocol — draft
Status: proposed, not frozen. No new experimental results.

## Research question
Does owner-qualified SHACL grounding with deterministic compilation improve supported-query correctness and unsupported-request handling relative to schema-informed direct SPARQL? Does owner qualification itself contribute beyond structured planning?

## Methods
A: direct SPARQL generation with schema, graph and registered mapping information; no reference queries, expected domains or answers.
B: same structured planner and compiler as C, but remove owner-qualified path descriptions from the model-facing candidate view; retain opaque candidate IDs and internal registry. Document any remaining ownership cues and keep candidate sets identical.
C: full existing TEP NEXUS expanded retrieval and compiler.
Use the same model version, decoding settings, question set, data snapshot, inference settings, timeout and read-only execution policy. Record actual prompt contents, token counts, model digest and hardware. Report differences in prompt budgets rather than claiming identical information exposure. No oracle routing or rejection before model output is scored.

## Benchmark integrity gate
The existing 46 scenarios and 230 questions are candidate material. Preserve historical runs. Independently review each reference against the intended owner, projection roles, filters, join keys and expected multiplicity. Resolve SD11/SD12 overlapping OR branches and SD13/SD14/CD15–18 ordering ties explicitly. Empty-result cases E45/E46 require structural review. Review all six negative contracts; distinguish explicit refusal/clarification, invalid output, policy-blocked query and erroneous accepted SELECT. Never execute writes. Record hashes of frozen manifest, references, schema, mappings, graph registry and actual instance snapshot.
Do not label positional binding agreement as semantic equivalence. Require projection-role review and RDF term-aware multiset comparison; evaluate order only when specified and deterministic or tie-aware. Retain all failures in denominators.

## Ownership challenge (separate synthetic diagnostic)
Verify actual instance coverage using RDF parsing. Populate all seven ECAD LocalId ownership contexts, distinct LocalId/Address projections, shared identifiers and missing optional values. Validate against the actual SHACL template. Independently specify expected bindings and run reference queries and path mutation/discrimination tests. Verify production compiler with manually resolved plans before LLM evaluation. Keep fixture in an isolated graph and report separately from original engineering data. Do not tune methods on held-out challenge questions.

## Execution sequence
1. Audit and freeze benchmark and safety contracts.
2. Validate synthetic fixture and compiler; record actual outputs.
3. Implement A and B with shared scoring and safety policy.
4. Run paired smoke tests, resolve infrastructure defects without tuning on held-out questions.
5. Run all methods on frozen questions, initially Qwen2.5-Coder 7B; extend to other models for generality.
6. Report supported accuracy, execution and compilation rates, rejection outcomes, owner/path errors, end-to-end latency and token usage. Separate model failures from infrastructure failures. Report paired differences and scenario-clustered uncertainty (five lexical variants are not independent scenarios). Treat small synthetic diagnostic as descriptive.
7. Revise manuscript only after evidence is available; report null or adverse findings.

## Scope
No claim of superiority, SHACL conformance, semantic equivalence or Strong Accept is established by this protocol. Temporal retrieval evaluation is a separate workstream.
