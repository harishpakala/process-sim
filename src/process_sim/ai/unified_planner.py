"""Experimental Ollama router for existing engineering and temporal query plans.

Model output is a routing proposal, never executable SQL or SPARQL.
"""
from __future__ import annotations

import json
from urllib.request import Request, urlopen
from .planner import _local_url, query_structured
from .temporal_plan import execute_temporal_plan, validate_temporal_plan
from .temporal_registry import temporal_registry

OPERATIONS = ("runs", "signal_history", "asset_history", "asset_trace")

def query_unified(question, graphdb_endpoint, *, ollama_transport=None,
                  graphdb_transport=None, temporal_executor=None,
                  engineering_executor=None, ollama_endpoint="http://127.0.0.1:11434",
                  model="llama3.1:8b", domains=None):
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
        raise ValueError("Question must be 1..2000 characters")
    url = _local_url(ollama_endpoint)
    context = temporal_registry()
    prompt = (
        "Select exactly one safe query route. Return JSON with keys route and plan. "
        "route is temporal, engineering, cross_domain, or insufficient. For temporal, plan is "
        "an object using ONLY: {operation:runs,limit:int}; "
        "{operation:signal_history,runId:UUID,signal:XMEAS1..41 or XMV1..12,limit:int}; "
        "{operation:asset_history,runId:UUID,assetIri:absolute HTTP IRI,limit:int}. "
        "For cross_domain, plan must be {operation:asset_trace,assetId:string} "\n        "or {operation:asset_trace,assetId:string,runId:UUID,limit:int}. "\n        "For engineering or insufficient, plan must be null. "
        "Never invent run IDs, asset IRIs, signals, mappings, or physical installations. "
        "If required identifiers are missing choose insufficient. "
        "Never generate SQL or SPARQL."
    )
    body = {"model": model, "stream": False, "format": "json",
            "options": {"temperature": 0},
            "messages": [{"role": "system", "content": prompt},
                         {"role": "user", "content": json.dumps({
                             "question": question, "temporalVocabulary": context,
                             "engineeringDomains": domains
                         })}]}
    if ollama_transport is None:
        def ollama_transport(endpoint, payload):
            req = Request(endpoint, data=json.dumps(payload).encode("utf-8"),
                          headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=45) as response:
                return json.load(response)
    response = ollama_transport(url, body)
    try:
        proposal = json.loads(response["message"]["content"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid router response") from exc
    if not isinstance(proposal, dict) or set(proposal) != {"route", "plan"}:
        raise ValueError("Unexpected router fields")
    route = proposal["route"]
    if route == "insufficient" and proposal["plan"] is None:
        return {"status": "insufficient_schema", "route": route}
    if route == "cross_domain":\n        from .cross_domain_trace import execute_trace_plan, validate_trace_plan\n        validated = validate_trace_plan(proposal["plan"])\n        return {"status": "executed_unverified", "route": route,\n                "data": execute_trace_plan(validated, graphdb_endpoint)}\n    if route == "temporal":
        validated = validate_temporal_plan(proposal["plan"])
        if validated["operation"] == "asset_history" and temporal_executor is None:
            from .semantic_temporal_workflow import execute_asset_signal_workflow
            result = execute_asset_signal_workflow(validated)
        else:
            executor = temporal_executor or execute_temporal_plan
            result = executor(validated)
        return {"status": "executed_unverified", "route": route, "data": result}
    if route == "engineering" and proposal["plan"] is None:
        executor = engineering_executor or query_structured
        return executor(question, graphdb_endpoint, domains=domains,
                        ollama_transport=ollama_transport,
                        graphdb_transport=graphdb_transport,
                        ollama_endpoint=ollama_endpoint, model=model)
    raise ValueError("Unsupported route or invalid plan")
