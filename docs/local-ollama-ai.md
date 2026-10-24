# Local Ollama grounded AI foundation (experimental)

This is a **read-only research prototype**, not a verified engineering decision system. It uses deterministic keyword retrieval from an explicit allowlist of repository documentation, followed by local Ollama generation. It does not access GraphDB, ECAD JSON, review databases, simulation state or OPC UA. No source engineering records are modified.

From repository root:

```bash
export PYTHONPATH=src
ollama pull llama3.1:8b
ollama serve
python -m unittest discover -s tests -p 'test_ai_grounded.py'
python -c 'from pathlib import Path; from process_sim.ai.grounded import answer; print(answer("What is the physical BOM governance status?", Path(".")))'
```

Ollama defaults to http://127.0.0.1:11434. Pass `model=` to select another locally installed model. A response status of `cited_unverified` means citation tokens reference retrieved lines, **not** that the factual statements are verified. No citation or invalid citation causes abstention. Prompt injection, hallucination and source mismatch remain possible; independent verification is required before operational use.

Next steps: structured engineering entity extraction, semantic identity resolution, trusted retrieval from validated RDF/SPARQL with access controls, factual entailment evaluation, and offline benchmark fixtures. Never use generated text to authorize physical BOM promotion or operational controls.
