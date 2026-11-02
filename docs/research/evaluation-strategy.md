# Research evaluation strategy — evidence-grounded industrial AI

**Status (25 October 2026): evaluation protocol proposed; systematic benchmark results are not yet available.** This plan supports the research direction *Towards Evidence-Grounded AI in Industrial Automation: A Semantic Reference Architecture*. The architecture is intended to be reusable across industrial automation systems; **TEP NEXUS is the initial reference implementation**, not evidence of general portability. The evaluation follows a two-level principle inspired by the component-level and end-to-end evaluation design of *Req2Road* (CAiSE 2026, [arXiv:2602.15591](https://arxiv.org/abs/2602.15591)); its experiments and outcomes are not claimed to be equivalent.

### Evaluation questions

- **RQ1 — Semantic identity:** Can AssetInventory assets be resolved to the correct, unambiguous operational signals and historical observations?
- **RQ2 — Evidence traceability:** Can each supported engineering statement be traced to the right asset, simulation run, observations, timestamps, and data source?
- **RQ3 — Claim reliability:** Do independent numerical/temporal checks and evidence-bounded responses reduce unsupported statements and improve appropriate abstention compared with less-constrained baselines?
- **RQ4 — Portability (future):** Which architectural contracts can be reused in a second automation environment without TEP-specific assumptions?

### Component-level experiments

| ID | Experiment | Procedure and ground truth | Primary measures |
|---|---|---|---|
| **E1** | Semantic asset-to-signal resolution | Audit the 41 XMEAS and 12 XMV signal identities against explicit AssetInventory operational references; manually adjudicate ambiguous or missing links. Do not assume full mapping coverage. | Mapping coverage, precision/recall on adjudicated cases, false-link and ambiguity-detection rates |
| **E2** | Run-specific evidence retrieval and provenance | Query multiple recorded runs; compare returned observations, run IDs, ordering, values, and timestamps against independent historian queries and recorded manifests. Include nonexistent runs and missing data. | Evidence retrieval accuracy, run/time consistency, attribution accuracy, missing-evidence handling |
| **E3** | Numerical and temporal claim verification | Construct correct and deliberately corrupted statements about latest values, deltas, direction, timestamps, and run identity; test independent checks. | Detection precision/recall, false rejection rate, unsupported numerical/temporal claim rate |
| **E4** | Evidence-grounded AI reliability | Evaluate the same question set across controlled baseline configurations, including answerable and unanswerable questions. Independently adjudicate semantic and causal assertions. | Answer correctness, claim faithfulness, appropriate abstention, false causal attribution, latency |

**Fault-aware cases** may use seeded TEP disturbances and fault events to test retrieval of recorded fault context. An injected fault label does **not** by itself prove that a specific measurement change has a unique cause. Full root-cause analysis remains planned and must not be reported as an evaluated capability.

### Baselines and ablations

Use the same model version, question set, generation settings, and comparable evidence windows where applicable. Record exactly what each configuration receives:

| Configuration | Input and mechanisms | Purpose |
|---|---|---|
| **B1 — Ungrounded LLM** | Question and general scenario description; no retrieved operational measurements | Measure unsupported answering without access to evidence; **not** a fair numerical-information baseline |
| **B2 — Historical-evidence LLM** | Question plus historian observations with signal, run, and time context | Test whether supplying operational evidence is sufficient |
| **B3 — Semantic-grounded LLM** | B2 plus explicit AAS/GraphDB asset resolution and provenance | Isolate the benefit of semantic binding and source attribution |
| **B4 — Semantic grounding + verification** | B3 plus independent claim checks, rejection/repair policy, and evidence-bounded abstention | Test verification benefits and costs |

For a controlled **verification ablation**, compare B3 and B4 on *identical retrieved evidence*. For a **semantic-resolution ablation**, evaluate cases where identity is genuinely ambiguous or mismatched; do not attribute gains to semantics when the baselines already receive the correct identity. Record deterministic responses separately from model-generated responses: a rule-based answer is **not** an LLM answer that passed verification.

### End-to-end feasibility

Demonstrate a reproducible engineering question through:

```text
Engineering question
    -> AssetInventory identity / GraphDB operational reference
    -> Run-specific TimescaleDB observations
    -> Evidence package (source, identity, run, time, values)
    -> Numerical / temporal verification
    -> Evidence-bounded answer or explicit abstention
```

Capture the exact query, asset IRI, signal, run ID, source observations, expected result, produced answer, verification status, and latency. Report any stages not exercised live; an existing historical query path does not automatically establish continuous OPC UA-to-historian-to-graph synchronization. No MES or standalone ERP integration is currently demonstrated.

### Benchmark design and reproducibility

- **Initial target, not a result:** audit up to 53 operational signals; collect 5–10 reproducible runs and approximately 30–50 manually reviewed engineering scenarios as a feasibility benchmark. Expand to 150–250 questions and repeated LLM trials if resources permit.
- Include factual retrieval, trend/delta, run-specific, missing-evidence, ambiguous-mapping, unsupported-causality, and (if implemented) fault-context questions.
- Create ground-truth records independently of model output using historian queries, graph assertions, controlled simulation manifests, and human review for ambiguous or causal cases.
- Pin code commit, graph snapshot, database snapshot/run IDs, model identifier/version, prompts, seeds where supported, temperature, hardware, and timeouts. Preserve per-question inputs, outputs, decisions, and timings.
- Report per-category denominators, failure examples, uncertainty intervals where justified, and threats to validity. Do not generalize from a single process, model, or corrected answer to all industrial systems.

### Current evidence and limits

- A previously recorded TEP run contains **145,856 signal samples**, covering **53 signals** and **2,752 timestamps**; selected asset-history values were compared with the historian.
- In one XMEAS6 historical question, an Ollama response incorrectly characterized a decrease as unchanged. A subsequent **deterministic** response correctly computed the delta and declined unsupported causal attribution. This demonstrates a specific failure and mitigation, **not** a measured overall reliability improvement.
- A valid asset with a nonexistent run produced a `NO_EVIDENCE` result. More negative cases and an automated regression suite are required.
- The current historical Q&A CLI uses TEP-specific signal validation; reuse outside TEP is a design objective, not yet an evaluated property.
- Numerical token screening is not full semantic verification. The present causal-question path bypasses the LLM and should be analyzed as a distinct deterministic response policy.

**Minimum publishable evaluation package:** E1–E4 with independently established ground truth, B2/B3/B4 comparisons, at least one complete traceable workflow, negative cases, reproducible artifacts, and an explicit limitations discussion. The evaluation plan does not predetermine positive results.
