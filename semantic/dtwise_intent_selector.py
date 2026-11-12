"""Grounded semantic-intent selection over DTWise candidates via local Ollama.

Run:
  python -m semantic.dtwise_intent_selector --query "EngineeringBOM instrument asset identifier"
No SPARQL is generated here. The LLM may only select offered candidate IDs.
"""
import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from semantic.dtwise_concept_resolver import resolve_compact

SYSTEM = """You select ontology concepts for a natural-language question.
Reply with exactly one JSON object, no markdown:
{"selected_ids":["C1"],"intent":"lookup","value_constraints":[]}
Select ONLY candidate IDs in the provided candidates list.
Prefer the property directly requested. Do not select unrelated identifier types.
Do not invent ontology IRIs, mappings, joins, or instance values.
If the question cannot be grounded, return an empty selected_ids list.
value_constraints must be an array of objects with "text" and "role" strings.
Only include values explicitly present in the user's question.
"""

def _extract_json(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError("Model did not return a JSON object")
        return json.loads(match.group(0))


def select_intent(index, question, model="qwen2.5-coder:3b",
                  endpoint="http://localhost:11434", limit=10, timeout=90):
    bundle = resolve_compact(index, question, limit=limit)
    allowed = {item["id"]: item for item in bundle["candidates"]}
    prompt = json.dumps(bundle, ensure_ascii=False)
    payload = {
        "model": model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        reply = json.load(response)
    model_text = reply.get("message", {}).get("content", "")
    parsed = _extract_json(model_text)
    if not isinstance(parsed, dict):
        raise ValueError("Model output must be an object")
    ids = parsed.get("selected_ids", [])
    if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
        raise ValueError("selected_ids must be a list of strings")
    invalid = sorted(set(ids) - set(allowed))
    if invalid:
        raise ValueError("Model selected unknown IDs: " + ", ".join(invalid))
    selected_ids = list(dict.fromkeys(ids))
    constraints = parsed.get("value_constraints", [])
    if not isinstance(constraints, list):
        raise ValueError("value_constraints must be a list")
    checked_constraints = []
    for constraint in constraints:
        if not isinstance(constraint, dict):
            raise ValueError("Invalid value constraint")
        value = constraint.get("text")
        role = constraint.get("role")
        if not isinstance(value, str) or not value.strip() or not isinstance(role, str):
            raise ValueError("Invalid value constraint fields")
        # Ground extracted values in the original question, not the model response.
        if value.casefold() not in question.casefold():
            raise ValueError("Model invented a value constraint: " + value)
        checked_constraints.append({"text": value, "role": role})
    return {
        "question": question,
        "model": model,
        "selected_ids": selected_ids,
        "selected_concepts": [allowed[i] for i in selected_ids],
        "intent": parsed.get("intent", "") if isinstance(parsed.get("intent", ""), str) else "",
        "value_constraints": checked_constraints,
        "join_status": "unverified",
        "sparql_generated": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path,
                        default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    parser.add_argument("--query", required=True)
    parser.add_argument("--model", default="qwen2.5-coder:3b")
    parser.add_argument("--endpoint", default="http://localhost:11434")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    index = json.loads(args.index.read_text(encoding="utf-8"))
    try:
        result = select_intent(index, args.query, args.model, args.endpoint, args.limit)
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(1, "Grounded intent selection failed: " + str(exc) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
