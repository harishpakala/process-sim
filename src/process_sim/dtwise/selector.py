"""Local Ollama ontology candidate selector for DTwise.

Compatible with ConceptSelector(model_name, ollama_host).select(question, hits).model_dump().
The selector does not validate full ontology paths; use the schema graph for that.
"""

import json
from typing import List

from ollama import Client
from pydantic import BaseModel, Field


class Selection(BaseModel):
    selected_ids: List[str] = Field(default_factory=list)
    explanation: str = ""


class _ModelSelection(BaseModel):
    selected_refs: List[str] = Field(default_factory=list)
    explanation: str = ""


class ConceptSelector:
    def __init__(self, model_name="qwen2.5-coder:3b", ollama_host="http://localhost:11434"):
        self.client = Client(host=ollama_host,timeout=10000.0)
        self.model_name = model_name

    def select(self, question, candidates):
        if not candidates:
            return Selection()

        compact = []
        ref_to_id = {}
        for i, item in enumerate(candidates, start=1):
            ref = f"C{i}"
            ref_to_id[ref] = item["id"]
            entry = {
                "ref": ref,
                "type": item.get("type", ""),
                "kind": item.get("kind", ""),
                "domain": item.get("domain", ""),
                "labels": item.get("labels", [])[:4],
                "text": item.get("text", "")[:170],
            }
            if item.get("type") == "relationship" or item.get("kind") == "relationship":
                entry.update({
                    "subject": item.get("subject", ""),
                    "predicate": item.get("predicate", ""),
                    "object": item.get("object", ""),
                })
            elif item.get("uri"):
                entry["uri"] = item["uri"]
            compact.append(entry)

        instructions = (
            "You are selecting the MINIMAL sufficient set of DTwise ontology records "
            "for answering a user's schema question. Records are schema definitions, "
            "not actual device instances. Select only directly necessary concepts, "
            "properties, SHACL paths, and connecting relationships. "
            "Do not select a record merely because it shares a domain or keyword. "
            "For a traversal question, retain the relevant connecting SHACL records. "
            "Do not assume a join or path exists unless supported by supplied records. "
            "Do not invent records, device instances, or relationships. "
            "You may select zero records if none suffice. "
            "Use only C-number refs provided in the candidates. "
            "Return a short explanation identifying the essential path or why it is incomplete."
        )
        payload = {"question": question, "candidates": compact}
        response = self.client.chat(
            model=self.model_name,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            format=_ModelSelection.model_json_schema(),
            options={"temperature": 0, "num_predict": 256, "num_ctx": 4096},
            keep_alive="10m",
        )
        parsed = _ModelSelection.model_validate_json(response.message.content)
        selected = []
        seen = set()
        for ref in parsed.selected_refs:
            original_id = ref_to_id.get(ref)
            if original_id is not None and original_id not in seen:
                selected.append(original_id)
                seen.add(original_id)
        return Selection(selected_ids=selected, explanation=parsed.explanation)


# Optional backwards-compatible name for any code importing OllamaSelector.
OllamaSelector = ConceptSelector
