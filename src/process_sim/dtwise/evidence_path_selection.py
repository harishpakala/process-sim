"""Experimental LLM semantic selection over pre-enumerated SHACL evidence paths.

Not connected to generate_ir: the established direct planner remains unchanged.
The model selects a candidate ID or abstains; it never supplies edge IRIs.
"""
import json
import re


def select_evidenced_path(question, paths, *, model, request_json,
                         ollama_host="http://localhost:11434", timeout=120,
                         keep_alive=None):
    """Return (selected_path_or_None, diagnostics) from LLM path-ID selection.

    Paths must be produced by enumerate_evidenced_paths using verified evidence.
    The caller is responsible for validating any subsequently constructed IR.
    request_json(url, payload, timeout) is injected for offline testing.
    """
    if not isinstance(question, str) or not question.strip():
        raise ValueError("A nonempty question is required")
    if not isinstance(paths, list) or not 1 <= len(paths) <= 32:
        raise ValueError("Provide 1 to 32 evidenced candidate paths")
    if not callable(request_json):
        raise TypeError("request_json must be callable")
    choices = []
    for i, path in enumerate(paths):
        if not isinstance(path, dict):
            raise ValueError("Invalid evidence path")
        nodes, steps = path.get("nodes"), path.get("steps")
        if (not isinstance(nodes, list) or not isinstance(steps, list)
                or len(nodes) != len(steps) + 1 or not steps):
            raise ValueError("Invalid evidence path structure")
        if any(not isinstance(n, (tuple, list)) or len(n) != 2
               or not all(isinstance(x, str) and x for x in n)
               for n in nodes):
            raise ValueError("Invalid evidence path nodes")
        if any(not isinstance(step, dict) or
               (step.get("kind") == "shacl" and not step.get("predicate")) or
               (step.get("kind") == "mapping" and not all(
                   step.get(k) for k in ("mapping_id", "left_predicate",
                                         "right_predicate"))) or
               step.get("kind") not in ("shacl", "mapping")
               for step in steps):
            raise ValueError("Invalid evidence path steps")
        choices.append({"id": f"PATH_{i}", "nodes": nodes, "steps": steps})
    payload = {
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content":
             "Choose the single evidence path that best answers the user's "
             "question. Only return JSON with a choice equal to one listed "
             "PATH ID, or null if no path matches. Do not invent edges, "
             "predicates, or a new path."},
            {"role": "user", "content": json.dumps(
                {"question": question, "choices": choices},
                separators=(",", ":"))},
        ],
    }
    if keep_alive is not None:
        payload["keep_alive"] = keep_alive
    response = request_json(ollama_host.rstrip("/") + "/api/chat",
                            payload, timeout)
    raw = response.get("message", {}).get("content", "")
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None, {"status": "invalid_response", "raw": raw}
    choice = parsed.get("choice") if isinstance(parsed, dict) else None
    if choice is None:
        return None, {"status": "abstained", "raw": raw}
    if not isinstance(choice, str) or not re.fullmatch(r"PATH_[0-9]+", choice):
        return None, {"status": "invalid_choice", "raw": raw}
    index = int(choice[5:])
    if index >= len(paths):
        return None, {"status": "invalid_choice", "raw": raw}
    return paths[index], {"status": "selected", "choice": choice, "raw": raw}
