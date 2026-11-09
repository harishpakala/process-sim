# TEP NEXUS Q1–Q12: manual answer-assessment rubric

## Scope and controls

Apply this rubric to **evidence-conditioned Ollama QA**, not live VTKG query execution. The evaluation script reports evidence availability, but does not automatically grade answer correctness. Assess each answer independently against its question and the evidence snapshot. Preserve `manual_assessment: null` until a human reviewer has assessed it. The questions are fixed for the comparison; only grounding instructions change. Use the same model, run ID, data sources, and time window. This is a development comparison, not held-out validation.

## Rating criteria

- **PASS**: All requested material facts are correct and adequately complete, with no materially misleading unsupported claims. Minor irrelevant qualifications may be noted without failing.
- **PARTIAL**: Requested facts are mostly correct, but a material requested item is missing, an explicit mapping is wrongly treated as uncertain, or an unsupported interpretation creates meaningful ambiguity.
- **FAIL**: Key requested identifiers, values, or conclusions are wrong or absent, or the answer claims verified fault activation without evidence in a way that invalidates its central conclusion.
- **NOT_ASSESSED**: No human assessment has been completed; do not infer PASS from `EVIDENCE_AVAILABLE`.

For each question, record the rating, supporting evidence keys, any omissions, any unsupported assertions, and a concise justification. If a field is unavailable, acknowledging that absence is correct; do not penalize justified uncertainty.

## Per-question expected evidence and checks

| ID | Expected facts | Common errors to flag |
|---|---|---|
| Q1 | Four reactor-associated logical instruments: pressure PI-1101 / XMEAS7, feed-flow FI-1101 / XMEAS6, temperature TI-1101 / XMEAS9, level LI-1101 / XMEAS8 | Treating physical installation as verified |
| Q2 | ECAD local device identifiers: PI-1101, FI-1101, TI-1101, LI-1101 | Confusing ECAD identifiers with signal IDs or electrical terminal/wiring references |
| Q3 | PI101 → XMEAS7; FI106 → XMEAS6; TI101 → XMEAS9; LI101 → XMEAS8, with canonical `https://aas.example.com/` URI prefix | Missing a canonical URI or signal |
| Q4 | Pressure Endress+Hauser PMP51B candidate; flow Endress+Hauser TMass F300 candidate; temperature IFM TA1101; level Endress+Hauser FMR62B candidate | Presenting product candidates as verified installed models |
| Q5 | Pressure ECLASS 27-27-49-05 / QUDT BAR; flow 27-20-04-03 / KiloGM-PER-HR; temperature 27-27-51 / DEG_C; level 27-20-05-05 / M and MilliM; distinguish catalog properties from verified physical characteristics | Assigning product-family ranges or accuracy to an installed device without evidence; conflating ECLASS classification and IRDI verification |
| Q6 | Same four canonical asset URIs join DEXPI, ECAD and AssetInventory logical representations | Claiming direct mappings absent when graph evidence explicitly provides them |
| Q7 | PI-1101: DEXPI PI_101, ECAD PI-1101, AssetInventory URI `https://aas.example.com/PI101`, Endress+Hauser PMP51B product candidate, XMEAS7 | Confusing canonical URI with local identifier; claiming verified installation |
| Q8 | `paper-fault-01` operator `inject` command recorded at simulation time 30 s; no independent activation proof in supplied evidence | Calling the command proof of fault activation |
| Q9 | At 27 s → 30 s: XMEAS6 42.59676165856366 → 42.12749043629619; XMEAS7 2704.620214463725 → 2705.2296678024463; XMEAS8 75.85021270847888 → 74.97687917695812; XMEAS9 120.37951958596531 → 120.39829605894376 | Calling the 30 s observations 'post-fault' or inferring causation |
| Q10 | FI-1101: `https://aas.example.com/FI106`, DEXPI FI_106, ECAD FI-1101, product `EandH_TMass_F300_Candidate`, ECLASS 27-20-04-03, XMEAS6; values 42.59676165856366 at 27 s and 42.12749043629619 at 30 s | Unwarranted doubt about explicit canonical mapping; treating 30 and 30.0 as distinct |
| Q11 | Temperature product candidate IFM_TA1101 has ECLASS IRDI `0173-1#01-AHB186#005`; ECLASS verification pending | Treating candidate IRDI as independently verified for an installed instrument |
| Q12 | Return all 22 recorded XMEAS9 observations in inclusive 0–60 s window, from 0 s through ~59 s; no observation at 60 s; distinguish historian simulation time from `observed_at` | Inventing units or timing discrepancies; treating absence of 60 s sample as query failure |

## Interpretation safeguards

Logical asset reconciliation and graph mapping do not establish physical installation. ProductCatalog measurement units describe product attributes; they do not automatically establish the units of raw TimescaleDB XMEAS values. The 30 s command and samples are temporally adjacent, but the supplied evidence does not independently verify fault activation or causality. Floating-point representations such as `27.000000000000004` are numerically equivalent to 27 s at the shown precision.

## Reporting template

For each Q1–Q12, record: `id`, `manual_assessment` (PASS/PARTIAL/FAIL), `assessment_justification`, `supported_facts`, `missing_facts`, and `unsupported_claims`. Report separate aggregates for evidence availability and manually judged answer quality. Preserve the raw generated answer and evidence SHA-256 for auditability.
