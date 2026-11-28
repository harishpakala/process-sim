# Comparative experiment freeze candidate

Status: pending final readiness checks; not a completed freeze.

Implementation and pilot evidence baseline: 0dbaa955a2b19ab54d6bf0fba8f9cce3638fb0a0.
Gold report SHA-256: b13415867bad62aecba800575935bb20b8e525050ac3f6348aaf040ba141c1b1.

## Design
Retain all 275 questions (55 scenarios, five lexical variants each), including 250 supported and 25 negative questions. Exclude write requests. Evaluate direct, ablated and full methods with qwen2.5-coder:7b, llama3.1:8b and mistral:7b: 2475 attempts. No pilot-driven planner tuning. Record model digests, runtime configuration, hardware, graph snapshot and inference setting. Use the same questions, gold, timeout policy and dataset across methods. Preserve raw records and count failures in the denominator.

## Pilot (development evidence)
Qwen only: direct 30/40 supported correct, 0/5 correct rejections; ablated 40/40 and 5/5; full 39/40 and 5/5. AI-assisted structural review, not independent adjudication. Strict projection arity applies to all methods; missing named-graph scoping is a documented dataset-specific limitation. The ablation removes explicit owner presentation only, not owner-aware retrieval or validation. No claim of full-method superiority over ablated. Pilot questions overlap the full benchmark; report this exposure and a sensitivity analysis excluding the nine pilot scenarios.

## Remaining readiness checks
- Verify unrestricted ordered references for SD13, SD14, CD15–CD18 against current gold, including ties and projected roles.
- Verify graph snapshot identity and record model digests/settings.
- Confirm direct baseline prompt fits each model and document any technical failures.
- Freeze review policy and obtain independent adjudication; retain AI-assisted labels separately.
- Validate complete run coverage and paired scenario-clustered analysis. Do not treat five lexical variants as independent observations.

Do not declare final freeze until these checks are recorded. No new model executions are needed to archive the pilot.
