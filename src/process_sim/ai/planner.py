"""Ontology-aware local Ollama SPARQL planner with a validated execution path."""

# Created: 2026-10-23
# Author: Harish
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .graphdb import select
from .semantic_registry import build_registry, planner_context
from .sparql_policy import validate_select

SYSTEM = (
    "You plan read-only RDF graph queries. Return ONLY JSON with one key 'sparql' "
    "containing a SELECT query with LIMIT 1..200. Use ONLY predicates and named "
    "graphs supported by the source AAS lifting conventions. Use explicit full IRIs, not PREFIX abbreviations. Do not use SERVICE, FROM, "
    "updates, or invented relationships. If the schema is insufficient, return "
    '{"sparql": null}. Do not infer verified installation from semantic links.'
)

def _local_url(endpoint: str) -> str:
    p = urlsplit(endpoint)
    if p.scheme != "http" or p.hostname not in ("localhost", "127.0.0.1", "::1") or p.username or p.password or p.query or p.fragment or p.path not in ("", "/"):
        raise ValueError("Ollama must use a local HTTP loopback endpoint")
    return endpoint.rstrip("/") + "/api/chat"

def plan(question: str, schema: dict, *, endpoint: str = "http://127.0.0.1:11434",
         model: str = "llama3.1:8b", transport=None) -> dict:
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
        raise ValueError("Question must be 1..2000 characters")
    url = _local_url(endpoint)
    if transport is None:
        def transport(url, payload):
            request = Request(url, data=json.dumps(payload).encode("utf-8"),
                              headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=45) as response:
                return json.load(response)
    payload = {"model": model, "stream": False, "format": "json",
               "options": {"temperature": 0},
               "messages": [{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": json.dumps({
                                "question": question, "semantic_registry": schema
                            })[:16000]}]}
    result = transport(url, payload)
    raw = result.get("message", {}).get("content", "")
    try:
        proposal = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("Ollama did not return valid JSON") from exc
    if not isinstance(proposal, dict) or set(proposal) != {"sparql"}:
        raise ValueError("Unexpected planner output")
    return proposal

def query(question: str, graphdb_endpoint: str, *, ollama_transport=None,
          graphdb_transport=None, ollama_endpoint: str = "http://127.0.0.1:11434",
          model: str = "llama3.1:8b") -> dict:
    registry = build_registry()
    schema = planner_context(registry)
    proposal = plan(question, schema, endpoint=ollama_endpoint, model=model,
                    transport=ollama_transport)
    sparql = proposal["sparql"]
    if sparql is None:
        return {"status": "insufficient_schema", "schema": schema, "sparql": None, "bindings": []}
    validate_select(sparql)
    # Conservative IRI check: allow declared predicates/classes and standard RDF/AAS
    # vocabulary. This intentionally rejects instance IRIs until AST role analysis exists.
    allowed = {p["iri"] for d in registry["domains"] for p in d["predicates"]}
    allowed.update(c for d in registry["domains"] for c in d["classes"])
    allowed.update({
        "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
        "http://www.w3.org/2000/01/rdf-schema#label",
        registry["aasNamespace"] + "hasSubmodelElement",
        registry["aasNamespace"] + "value",
        registry["aasNamespace"] + "first",
        registry["aasNamespace"] + "second",
    })
    unknown = set(re.findall(r"<([^>]+)>", sparql)) - allowed
    if unknown:
        raise ValueError("Query references unregistered IRIs (conservative prototype): " +
                         ", ".join(sorted(unknown)[:5]))
    result = select(graphdb_endpoint, sparql, transport=graphdb_transport)
    return {"status": "executed_unverified", "sparql": sparql,
            "schema": schema, "bindings": result["results"]["bindings"],
            "note": "Execution is not evidence of answer correctness; no automatic answer synthesis yet."}


# Experimental structured-planning path. Unlike query(), the model cannot
# supply executable SPARQL here; only a plan validated against lifted SHACL.
def query_structured(question: str, graphdb_endpoint: str, *,
                     domains=None, ollama_transport=None, graphdb_transport=None,
                     ollama_endpoint: str = "http://127.0.0.1:11434",
                     model: str = "llama3.1:8b") -> dict:
    from .shacl_registry import build_shacl_registry, planner_shacl_context
    from .query_plan import validate_plan

    registry = build_shacl_registry()
    context = planner_shacl_context(registry, domains=domains, max_paths=500)
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
        raise ValueError("Question must be 1..2000 characters")
    endpoint = _local_url(ollama_endpoint)
    prompt = (
        "Return only JSON with exactly domain, path, limit. "
        "path is a list of full predicate IRIs forming a parentPredicate chain "
        "in the supplied SHACL paths. Never invent predicates, infer physical "
        "installation, or return SPARQL. If insufficient, return null."
    )
    payload = {"model": model, "stream": False, "format": "json",
               "options": {"temperature": 0},
               "messages": [{"role": "system", "content": prompt},
                            {"role": "user", "content": json.dumps({
                                "question": question, "shacl": context
                            })}]}
    if len(payload["messages"][1]["content"]) > 60000:
        raise ValueError("Planner context too large; scope domains")
    if ollama_transport is None:
        def ollama_transport(url, body):
            request = Request(url, data=json.dumps(body).encode("utf-8"),
                              headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=45) as response:
                return json.load(response)
    response = ollama_transport(endpoint, payload)
    try:
        proposed = json.loads(response["message"]["content"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid structured planner response") from exc
    if proposed is None:
        return {"status": "insufficient_schema", "bindings": [], "sparql": None}
    validated = validate_plan(proposed, registry)
    rows = select(graphdb_endpoint, validated.sparql, transport=graphdb_transport)
    return {"status": "executed_unverified", "domain": validated.domain,
            "path": list(validated.path), "sparql": validated.sparql,
            "bindings": rows["results"]["bindings"],
            "note": "Validated template SHACL path; results not independently verified."}
