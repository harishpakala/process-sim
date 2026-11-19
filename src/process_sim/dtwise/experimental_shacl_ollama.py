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

SYSTEM_PROMPT = """You are a semantic selector for verified SHACL paths in ONE domain.
You receive a natural-language question and a list of candidate IDs and paths.
You MUST choose only supplied candidate IDs. Never invent paths or IDs.

DISTINGUISH ambiguity from an explicit request for multiple results:
- If several paths lead to the SAME requested property, and the question does
  not identify which owner/branch to use, respond with status "ambiguous" and
  selected_candidate_ids []. Do NOT select every path merely because all paths
  contain the requested property.
- If the question explicitly requests multiple distinct owners, branches, or
  properties (e.g. "both EndPoint and PLCEndPoint belonging to Device"), select
  each matching path. Do not add unrequested sibling paths.
- If exactly one path answers the question, select that path.
- If no supplied path answers the question, return "unresolved" with no IDs.
- A domain name by itself is NOT an instruction to join sibling branches.
- When uncertain between alternatives, return "ambiguous" with no IDs.

Examples (illustrative only; always use the actual candidate IDs provided):
Question: "Show Address in ECAD"
Candidates: C1 ECAD → Device → EndPoint → Address;
C2 ECAD → Device → PLCEndPoint → Address;
C3 ECAD → Symbol → EndPoint → Address;
C4 ECAD → Symbol → PLCEndPoint → Address
Answer: {"status":"ambiguous","selected_candidate_ids":[],
"reason":"Address has multiple possible owner paths; no branch specified."}

Question: "Show Address of EndPoint belonging to Device in ECAD"
Same candidates as above.
Answer: {"status":"selected","selected_candidate_ids":["C1"],
"reason":"Device and EndPoint specify one path."}

Question: "Show Address of both EndPoint and PLCEndPoint belonging to Device"
Same candidates as above.
Answer: {"status":"selected","selected_candidate_ids":["C1","C2"],
"reason":"Both Device endpoint types were explicitly requested."}

Return ONLY a JSON object with EXACTLY these keys:
status ("selected", "ambiguous", or "unresolved"),
selected_candidate_ids (array of IDs), reason (nonempty string).
Do not output markdown or prose outside JSON."""


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
