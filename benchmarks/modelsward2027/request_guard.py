"""Conservative request-intent preflight for the read-only benchmark API."""
import re

WRITE = re.compile(r"^\s*(?:please\s+)?(?:delete|remove|erase|insert|update|modify|drop|clear|create|replace|add|perform\s+(?:a\s+)?deletion)\b",re.I)

def preflight(question):
    if not isinstance(question,str) or not question.strip():
        return {"decision":"clarify","reason":"empty_request"}
    if WRITE.match(question):
        return {"decision":"reject","reason":"write_operation"}
    return {"decision":"continue","reason":None}
