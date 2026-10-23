"""Ontology-aware local Ollama SPARQL planner with a validated execution path."""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .graphdb import discover_schema, select
from .sparql_policy import validate_select

SYSTEM = (
    "You plan read-only RDF graph queries. Return ONLY JSON with one key 'sparql' "
    "containing a SELECT query with LIMIT 1..200. Use ONLY predicates and named "
    "graphs explicitly listed in the observed schema. Do not use SERVICE, FROM, "
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
                                "question": question, "observed_schema": schema
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
    schema = discover_schema(graphdb_endpoint, transport=graphdb_transport)
    if not schema["observedPredicates"]:
        return {"status": "insufficient_schema", "schema": schema, "sparql": None, "bindings": []}
    proposal = plan(question, schema, endpoint=ollama_endpoint, model=model,
                    transport=ollama_transport)
    sparql = proposal["sparql"]
    if sparql is None:
        return {"status": "insufficient_schema", "schema": schema, "sparql": None, "bindings": []}
    validate_select(sparql)
    # Fail closed: require every explicitly named predicate IRI to be observed.
    allowed = {item["predicate"] for item in schema["observedPredicates"]}
    predicates = set(re.findall(r"<([^>]+)>", sparql))
    # Graph IRIs are allowed separately, but any non-schema IRI needs manual review.
    graphs = {item["graph"] for item in schema["observedPredicates"]}
    unknown = predicates - allowed - graphs
    if unknown:
        raise ValueError("Query contains unrecognized IRIs: " + ", ".join(sorted(unknown)[:5]))
    result = select(graphdb_endpoint, sparql, transport=graphdb_transport)
    return {"status": "executed_unverified", "sparql": sparql,
            "schema": schema, "bindings": result["results"]["bindings"],
            "note": "Execution is not evidence of answer correctness; no automatic answer synthesis yet."}
