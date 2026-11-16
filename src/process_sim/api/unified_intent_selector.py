"""Single semantic intent-selection step for the experimental unified planner.

The selector uses one bounded schema-aware model call for BOTH engineering and
observation questions. Downstream entity/temporal interpretation remains
specialized pending migration; no executable predicates come from model text.
"""
from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

from process_sim.dtwise.semantic_planner import _candidates


def _schema_catalog(schema):
    """Expose only domain and entity labels from SHACL-validated paths."""
    catalog = _candidates(schema)
    concepts = sorted({
        (c["domain"], str(label))
        for c in catalog for label in c["target_labels"]
    })
    return [{"domain": domain, "entity": label} for domain, label in concepts]


def _model_choice(question, catalog, *, host, model, timeout):
    system = (
        "You are a constrained semantic intent selector for DTWise. "
        "Choose whether the question requests graph relationships/properties "
        "(graph_query), historical time-series observations (observations), "
        "both (mixed), or is unsupported (unsupported). "
        "Use the supplied SHACL entity catalog as grounding context, not as "
        "permission to invent identifiers or relationships. "
        "Return ONLY a JSON object with one key: intent. "
        "Do not interpret graph relationship questions as observations just "
        "because they mention a simulation run."
    )
    payload = {
        "model": model, "stream": False, "format": "json",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps({
                "question": question, "shacl_entities": catalog
            })},
        ],
    }
    request = Request(
        host.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        body = json.load(response)
    return json.loads(body["message"]["content"])


def select_semantic_intent(question, schema, *, interpret=None,
                           host=None, model=None, timeout=60):
    """One bounded selection interface; never accept an unrecognized intent."""
    if not isinstance(question, str) or not 5 <= len(question.strip()) <= 1000:
        raise ValueError("Question must contain 5–1000 characters")
    catalog = _schema_catalog(schema)
    if not catalog:
        raise ValueError("No SHACL-validated entities available")
    if interpret is not None:
        choice = interpret(question, catalog)
    else:
        choice = _model_choice(
            question, catalog,
            host=host or os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            model=model or os.environ.get("DTWISE_QWEN_MODEL", "qwen2.5-coder:3b"),
            timeout=timeout,
        )
    if not isinstance(choice, dict) or set(choice) != {"intent"}:
        raise ValueError("Invalid semantic selector response")
    intent = choice["intent"]
    if intent not in ("graph_query", "observations", "mixed", "unsupported"):
        raise ValueError("Unsupported semantic intent")
    if intent == "unsupported":
        raise ValueError("Question has no supported semantic interpretation")
    return intent
