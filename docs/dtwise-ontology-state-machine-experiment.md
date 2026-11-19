# DTWise ontology exploration experiment

This branch introduces an **opt-in GRASP-inspired path exploration primitive**
(`ontology_state_machine.py`). It does not replace or modify the current
`hybrid` or `llm_first` experimental multi-hop modes.

## What works in this first increment

- Deterministic state transitions: OFFER VERIFIED EDGES -> LLM CHOOSES EDGE ->
  ADVANCE, until the supplied target is reached or a budget is exhausted.
- Each offered edge comes from existing SHACL `sh:node` evidence or a verified
  cross-domain mapping; edge IDs are ephemeral and strictly checked.
- No enumeration of complete multi-hop candidate paths is sent to the LLM.
- The final path is rebound into **existing Unified IR 1.0** with the existing
  `bind_evidenced_path` validator.
- A small Ollama JSON decision adapter and offline tests are included.

## Deliberate limitations

This is **not yet an end-to-end natural-language planner**. For a controlled
first comparison, the caller must provide start/end SHACL shapes and explicit
projection/filter requirements. OWL labels and descriptions are not retrieved
yet; the current evidence graph is SHACL + verified mappings. Only linear,
nonzero-hop SELECT paths are supported. The exploration is greedy and does not
backtrack. A valid but unhelpful LLM choice can exhaust its budget.

The current baseline's complete candidate-path selection may succeed where
this greedy approach fails. More sequential Ollama calls can also increase
latency. Neither correctness nor latency improvements are claimed.

## Offline test

```powershell
python -m unittest tests.test_dtwise_ontology_state_machine -v
```

## Comparison protocol (next increment)

Use the same grounded start/end, projections, GraphDB repository, Ollama
model, timeout and benchmark question for both approaches. Record:
- Exact answer-set equality, not just valid IR or SPARQL
- Number of LLM requests, prompt/output tokens and total elapsed time
- Number of evidence edges presented, hops and failure category

Do not compare this prototype with the existing B01-B04 results as if it
already supported all their operations. Add end-to-end integration and
benchmark adapters before claiming a 53-question comparison.
