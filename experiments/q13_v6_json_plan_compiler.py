#!/usr/bin/env python3
"""Q13-v6: ontology-grounded LLM JSON planning and deterministic SPARQL compilation.

Distinct method from direct NL-to-SPARQL baselines. No instance data, expected
answers or reference SPARQL are sent to Ollama. First attempt is never repaired.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from rdflib import Graph, URIRef
from rdflib.namespace import SH
from q13_v4_compact_shacl_ab import (
    ROOT, DEFAULT_QUESTION, load_ontologies, structural_validation,
    validate_query, evaluate, estimate_tokens
)
from q13_extract_focused_schema import extract

DOMAINS = ("dexpi", "ecad", "engineeringbom", "assetinventory",
           "opcuaconnectivity", "productcatalog")
BASE = {d: "https://example.org/" + d + "/" for d in DOMAINS}
SYSTEM = """You are an ontology-grounded query planner, NOT a SPARQL author.
Return a JSON plan selecting only exact predicate IRIs present in the provided
SHACL sh:path inventory. The six domains must be linked through equal asset
identifier values, and ProductCatalog through a product identifier. These
joins will be compiled deterministically, so do not write SPARQL.
Choose predicates for requested output fields from their domain's listed
properties. Choose a descriptive property for finding a temperature
measurement, never an opaque identifier. If no valid property exists for a
field, omit it rather than invent one. Do not assume instance values or
reference answers. Output JSON only."""
FIELDS = {
    "engineeringIdentifier": ("dexpi", "ecad", "engineeringbom"),
    "bomItemId": ("engineeringbom",),
    "sourceDomain": ("engineeringbom",),
    "inventoryTag": ("assetinventory",),
    "operationalSignal": ("opcuaconnectivity", "assetinventory"),
    "manufacturer": ("productcatalog",),
    "partNumber": ("productcatalog",),
}
JOIN_POLICY = {
    "asset": ["dexpi", "ecad", "engineeringbom", "assetinventory",
              "opcuaconnectivity"],
    "product": ["productcatalog", "assetinventory", "engineeringbom"],
    "semantics": "candidate RDF-term equality joins from shared identifier property local names; not owl:equivalentProperty",
}

def ontology_inventory():
    schema = extract()
    domain_props = {}
    compact = []
    for domain in schema["domains"]:
        d = domain["domain"]
        entries = {}
        shapes = []
        for shape in domain["node_shapes"]:
            props = []
            for prop in shape["properties"]:
                uri = prop["predicate"]
                entries[uri] = True
                props.append({"path": uri, **({"label": prop["label"]} if prop.get("label") else {}),
                              **({"datatype": prop["datatype"]} if prop.get("datatype") else {}),
                              **({"class": prop["value_class"]} if prop.get("value_class") else {})})
            shapes.append({"shape": shape["uri"], "targets": shape["target_classes"],
                           "properties": props})
        domain_props[d] = set(entries)
        compact.append({"domain": d, "shapes": shapes})
    return compact, domain_props

def verify_plan(plan, allowed):
    issues = []
    if not isinstance(plan, dict):
        return {}, ["Model response is not a JSON object."]
    fields = plan.get("fields")
    if not isinstance(fields, dict):
        return {}, ["Missing JSON object 'fields'."]
    cleaned = {}
    for name, selection in fields.items():
        if name not in FIELDS:
            issues.append("Unrecognized output field: " + str(name))
            continue
        if not isinstance(selection, dict):
            issues.append("Field selection must be an object: " + name)
            continue
        domain, uri = selection.get("domain"), selection.get("predicate")
        if domain not in FIELDS[name] or uri not in allowed.get(domain, set()):
            issues.append("Unsupported field mapping " + name + ": " + str(domain) + " " + str(uri))
        else:
            cleaned[name] = (domain, uri)
    if not cleaned:
        issues.append("No valid projected fields selected.")
    filter_obj = plan.get("description_filter")
    if not isinstance(filter_obj, dict):
        issues.append("Missing description_filter object.")
        filt = None
    else:
        d, uri, phrase = filter_obj.get("domain"), filter_obj.get("predicate"), filter_obj.get("text")
        local = uri.rsplit("/", 1)[-1].lower() if isinstance(uri, str) else ""
        if (d not in allowed or uri not in allowed.get(d, set())
                or not any(x in local for x in ("name", "description", "label", "designation", "text"))):
            issues.append("Description filter must select a declared descriptive predicate.")
            filt = None
        elif not isinstance(phrase, str) or phrase.lower() not in ("temperature", "reactor", "reactor temperature"):
            issues.append("Description filter text must be grounded in question terminology.")
            filt = None
        else:
            filt = (d, uri, phrase)
    return {"fields": cleaned, "filter": filt}, issues

def compile_query(plan, allowed):
    # These mandatory joins are derived from ontology predicate presence and
    # explicitly documented experiment integration policy, not model guesses.
    required = JOIN_POLICY["asset"]
    for d in required:
        if BASE[d] + "hasAssetIdentifier" not in allowed[d]:
            raise ValueError("Ontology lacks required asset join predicate in " + d)
    bridge = next((d for d in ("assetinventory", "engineeringbom")
                   if BASE[d] + "hasProductIdentifier" in allowed[d]), None)
    if not bridge or BASE["productcatalog"] + "hasProductIdentifier" not in allowed["productcatalog"]:
        raise ValueError("Ontology lacks required ProductIdentifier bridge.")
    patterns = []
    for d in required:
        patterns.append("?s_" + d + " <" + BASE[d] + "hasAssetIdentifier> ?assetId .")
    patterns.append("?s_productcatalog <" + BASE["productcatalog"] + "hasProductIdentifier> ?productId .")
    patterns.append("?s_" + bridge + " <" + BASE[bridge] + "hasProductIdentifier> ?productId .")
    selects = []
    for name, (domain, uri) in plan["fields"].items():
        var = "?" + name
        selects.append(var)
        patterns.append("?s_" + domain + " <" + uri + "> " + var + " .")
    filt = plan["filter"]
    if filt:
        d, uri, phrase = filt
        patterns.append("?s_" + d + " <" + uri + "> ?descriptionValue .")
        # Use JSON-escaped string literal to avoid SPARQL injection.
        patterns.append("FILTER(CONTAINS(LCASE(STR(?descriptionValue)), LCASE(" +
                        json.dumps(phrase) + ")))")
    if not selects:
        raise ValueError("No projected fields in validated plan.")
    return "SELECT DISTINCT " + " ".join(selects) + " WHERE {\n  " + "\n  ".join(patterns) + "\n}"

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", default="qwen2.5-coder:3b")
    p.add_argument("--ollama-url", default="http://localhost:11434")
    p.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    p.add_argument("--question", default=DEFAULT_QUESTION)
    p.add_argument("--num-ctx", type=int, default=12288)
    p.add_argument("--num-predict", type=int, default=800)
    p.add_argument("--max-prompt-estimate", type=int, default=7500)
    p.add_argument("--ollama-timeout", type=int, default=300)
    p.add_argument("--graphdb-timeout", type=int, default=60)
    p.add_argument("--skip-execution", action="store_true")
    p.add_argument("--output", default="reports/q13_v6_json_plan.json")
    args = p.parse_args()
    schemas, allowed_all = load_ontologies()
    inventory, allowed = ontology_inventory()
    payload = {"question": args.question, "ontology_shapes": inventory,
               "integration_policy": JOIN_POLICY, "requested_fields": FIELDS,
               "response_contract": {
                   "fields": {"fieldName": {"domain": "domainName", "predicate": "full sh:path IRI"}},
                   "description_filter": {"domain": "domainName", "predicate": "full descriptive sh:path IRI", "text": "temperature"}
               }}
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(payload, separators=(",", ":"))}]
    estimate = estimate_tokens(SYSTEM + messages[1]["content"])
    output = ROOT / args.output
    if output.exists():
        output = output.with_name(output.stem + "_" +
                                  datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + output.suffix)
    output.parent.mkdir(parents=True, exist_ok=True)
    audit = {"method": "q13_v6_ontology_grounded_json_plan_deterministic_compiler",
             "model": args.model, "question": args.question,
             "created_at_utc": datetime.now(timezone.utc).isoformat(),
             "first_attempt_only": True,
             "schema_sources": [{"file": s["file"], "sha256": s["sha256"]} for s in schemas],
             "prompt_estimate": estimate, "num_ctx": args.num_ctx,
             "num_predict": args.num_predict, "prompt_system": SYSTEM,
             "prompt_user": payload, "raw_model_response": None,
             "llm_plan": None, "plan_issues": [], "generated_sparql": None,
             "syntax_and_schema_issues": [], "structural_validation": None,
             "prompt_eval_count": None, "eval_count": None,
             "prompt_eval_duration_ns": None, "eval_duration_ns": None,
             "total_duration_ns": None, "time_to_first_chunk_seconds": None,
             "elapsed_seconds": None, "completed": False, "error": None,
             "graphdb_bindings": None, "evaluation": None}
    start = time.monotonic()
    try:
        budget = min(args.max_prompt_estimate, args.num_ctx - args.num_predict - 512)
        print("Preflight estimated tokens:", estimate, "budget:", budget, flush=True)
        if estimate > budget:
            raise ValueError("Preflight refused oversized prompt. No Ollama request sent.")
        chunks = []
        final = {}
        print("Streaming Ollama JSON plan; waiting for first chunk...", flush=True)
        with requests.post(args.ollama_url.rstrip("/") + "/api/chat",
                           json={"model": args.model, "messages": messages, "stream": True,
                                 "format": "json",
                                 "options": {"temperature": 0, "num_ctx": args.num_ctx,
                                             "num_predict": args.num_predict}},
                           stream=True, timeout=(10, args.ollama_timeout)) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                event = json.loads(line)
                if event.get("error"):
                    raise RuntimeError(event["error"])
                part = event.get("message", {}).get("content", "")
                if part:
                    if audit["time_to_first_chunk_seconds"] is None:
                        audit["time_to_first_chunk_seconds"] = round(time.monotonic() - start, 2)
                        print("First generated chunk after", audit["time_to_first_chunk_seconds"],
                              "seconds", flush=True)
                    chunks.append(part)
                    if len(chunks) % 50 == 0:
                        print("Received", len("".join(chunks)), "characters...", flush=True)
                if event.get("done"):
                    final = event
                    audit["completed"] = True
                    break
        raw = "".join(chunks)
        audit["raw_model_response"] = raw
        for k in ("prompt_eval_count", "eval_count"):
            audit[k] = final.get(k)
        for k in ("prompt_eval_duration", "eval_duration", "total_duration"):
            audit[k + "_ns"] = final.get(k)
        if not audit["completed"]:
            raise RuntimeError("Stream ended without Ollama done=true.")
        plan = json.loads(raw)
        audit["llm_plan"] = plan
        verified, issues = verify_plan(plan, allowed)
        audit["plan_issues"] = issues
        if issues:
            print("Plan rejected:", "; ".join(issues), flush=True)
        else:
            query = compile_query(verified, allowed)
            audit["generated_sparql"] = query
            syntax = validate_query(query, allowed_all)
            structure = structural_validation(query)
            audit["structural_validation"] = structure
            audit["syntax_and_schema_issues"] = syntax + structure["issues"]
            print("Compiled SPARQL:\n" + query, flush=True)
            if audit["syntax_and_schema_issues"]:
                print("Validation failed:", "; ".join(audit["syntax_and_schema_issues"]), flush=True)
            elif not args.skip_execution:
                result = requests.post(args.graphdb_url, data={"query": query},
                                       headers={"Accept": "application/sparql-results+json"},
                                       timeout=args.graphdb_timeout)
                result.raise_for_status()
                bindings = result.json()["results"]["bindings"]
                audit["graphdb_bindings"] = bindings
                audit["evaluation"] = evaluate(bindings)
                print("GraphDB bindings:", len(bindings), flush=True)
    except Exception as exc:
        audit["error"] = type(exc).__name__ + ": " + str(exc)
        print("ERROR:", audit["error"], file=sys.stderr, flush=True)
    finally:
        audit["elapsed_seconds"] = round(time.monotonic() - start, 2)
        output.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
        print("Audit saved:", output, flush=True)
    return int(bool(audit["error"] or audit["plan_issues"] or
                    audit["syntax_and_schema_issues"] or not audit["completed"]))

if __name__ == "__main__":
    sys.exit(main())
