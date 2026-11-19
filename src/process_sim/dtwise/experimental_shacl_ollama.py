"""Opt-in local Ollama semantic selector for one SHACL domain.

Only IDs from prepared verified paths can be returned. No external packages.
The default candidate retriever still relies on exact schema-name grounding.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from process_sim.dtwise.experimental_shacl_candidates import prepare_candidates
from process_sim.dtwise.experimental_shacl_selection import validate_selection
from process_sim.dtwise.experimental_shacl_subgraph import extract_question

SYSTEM_PROMPT = """You select verified SHACL paths for a question in ONE domain.
Only select IDs from the supplied candidates. Never invent paths or IDs.
Select all required independent paths when the question requests multiple properties.
If the question leaves multiple equally plausible interpretations, return ambiguous
with no IDs; do not guess. If no candidate answers the question, return unresolved
with no IDs. A domain mention alone does not imply a join between branches.
Return ONLY JSON with exactly these keys:
status ("selected", "ambiguous", or "unresolved"),
selected_candidate_ids (array of IDs), reason (nonempty string).
Do not output markdown or explanations outside JSON."""


def ollama_select(
    prompt: dict,
    *,
    model: str = "qwen2.5-coder:7b",
    endpoint: str = "http://127.0.0.1:11434",
    timeout: float = 120,
    transport=None,
) -> str:
    """Call local Ollama /api/chat; injectable transport enables offline tests."""
    if transport is None:
        def transport(url, payload, timeout):
            request = Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=timeout) as response:
                return json.load(response)

    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    }
    try:
        response = transport(endpoint.rstrip("/") + "/api/chat", payload, timeout)
        return response["message"]["content"]
    except (URLError, HTTPError, TimeoutError) as exc:
        raise RuntimeError("Ollama is unavailable; check that ollama serve is running") from exc
    except (KeyError, TypeError) as exc:
        raise RuntimeError("Unexpected Ollama response structure") from exc


def run_local_selection(
    index,
    question: str,
    *,
    model: str = "qwen2.5-coder:7b",
    endpoint: str = "http://127.0.0.1:11434",
    transport=None,
) -> dict:
    """Extract -> prepare -> local LLM -> validate, within index.domain only."""
    result = extract_question(index, question, connect=True)
    prepared = prepare_candidates(result)
    if not prepared["prompt"]["candidates"]:
        return {
            "domain": index.domain,
            "question": question,
            "selection": {
                "status": "unresolved",
                "selected_candidate_ids": [],
                "reason": "No SHACL candidates found by exact-name grounding",
            },
            "selected_paths": [],
        }
    raw = ollama_select(
        prepared["prompt"], model=model, endpoint=endpoint, transport=transport,
    )
    selection = validate_selection(raw, prepared)
    labels = {c["id"]: c["path"] for c in prepared["prompt"]["candidates"]}
    return {
        "domain": index.domain,
        "question": question,
        "selection": selection,
        "selected_paths": [
            {"id": candidate_id, "path": labels[candidate_id],
             "verified": prepared["registry"][candidate_id]}
            for candidate_id in selection["selected_candidate_ids"]
        ],
        "candidates": prepared["prompt"]["candidates"],
    }
