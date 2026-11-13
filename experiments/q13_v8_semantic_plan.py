#!/usr/bin/env python3
"""Q13-v8: focused ontology-only SHACL retrieval, strict JSON planning, deterministic SPARQL.

Experimental Q13-specific method, NOT a general custom-question engine.
Never supplies instances, expected bindings or reference queries to Ollama.
First attempt is preserved; no repair or silent field completion.
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import requests
from rdflib import URIRef
from q13_extract_focused_schema import extract
from q13_v4_compact_shacl_ab import ROOT, DEFAULT_QUESTION, load_ontologies, validate_query, structural_validation, evaluate

FIELDS = {
    "engineeringIdentifier": ["dexpi", "ecad", "engineeringbom"],
    "bomItemId": ["engineeringbom"],
    "sourceDomain": ["engineeringbom"],
    "inventoryTag": ["assetinventory"],
    "operationalSignal": ["opcuaconnectivity", "assetinventory"],
    "manufacturer": ["productcatalog"],
    "partNumber": ["productcatalog"],
}
ASSET_DOMAINS = ["dexpi", "ecad", "engineeringbom", "assetinventory", "opcuaconnectivity"]
PRODUCT_DOMAINS = ["productcatalog", "assetinventory", "engineeringbom"]
ALIASES = {
    "engineeringIdentifier": ["engineering", "identifier", "reference", "tag"],
    "bomItemId": ["bom", "item", "identifier"],
    "sourceDomain": ["source", "domain"],
    "inventoryTag": ["inventory", "tag", "name"],
    "operationalSignal": ["operational", "signal", "reference", "node"],
    "manufacturer": ["manufacturer", "brand"],
    "partNumber": ["part", "number", "model"],
}
DESCRIPTIVE = ("name", "description", "label", "designation", "measuredvariable", "measurement")
SYSTEM = """Only select properties whose names and labels semantically express the requested output. A product identifier is NOT an engineering identifier; an item description is NOT a BOM item ID. A property must also be on a SHACL shape compatible with the domain identifier join. If no matching predicate is available, mark the field unsupported.\nYou select SHACL property IRIs for a fixed engineering question. Do NOT write SPARQL.
Return exactly a JSON object with keys 'fields' and 'description_filter'.
'fields' MUST contain every requested field name, each mapped to either
{"domain":"...","predicate":"exact full IRI from candidate list"} or
{"unsupported":true}. Do not invent property IRIs.
'description_filter' must be {"domain":"...","predicate":"exact full IRI",
"text":"temperature"} or {"unsupported":true}.
Use a descriptive property for filtering, not opaque identifiers.
No instance values or reference answers are available. JSON only."""
def local(uri):
    return uri.rsplit("#", 1)[-1].rsplit("/", 1)[-1]

def tokenize(s):
    return set(re.findall(r"[a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", s).lower()))

def focused_inventory(schema, per_domain=14):
    """Rank all direct sh:path properties deterministically, preserving parent shapes."""
    selected = {}
    allprops = {}
    for domain in schema["domains"]:
        d = domain["domain"]
        choices = {}
        for shape in domain["node_shapes"]:
            for p in shape["properties"]:
                uri = p["predicate"]
                if uri not in choices:
                    choices[uri] = {"domain": d, "predicate": uri,
                                    "label": p.get("label"), "shape": shape["uri"],
                                    "target_classes": shape["target_classes"],
                                    "kind": p.get("kind"), "datatype": p.get("datatype")}
        allprops[d] = choices
        wanted = set()
        for f, domains in FIELDS.items():
            if d in domains:
                wanted.update(ALIASES[f])
        if d in ASSET_DOMAINS:
            wanted.update(["asset", "identifier"])
        if d in PRODUCT_DOMAINS:
            wanted.update(["product", "identifier"])
        if d in ("dexpi", "ecad", "engineeringbom"):
            wanted.update(["temperature", "reactor", "measured", "description", "name", "label"])
        scored = []
        for uri, p in choices.items():
            terms = tokenize(local(uri) + " " + (p["label"] or ""))
            score = len(terms & wanted) * 3
            if local(uri) in ("hasAssetIdentifier", "hasProductIdentifier"):
                score += 100
            if any(w in local(uri).lower() for w in DESCRIPTIVE):
                score += 5
            scored.append((score, uri))
        scored.sort(key=lambda t: (-t[0], t[1]))
        selected[d] = [choices[uri] for score, uri in scored[:per_domain] if score > 0]
    return selected, allprops

def discover_join(allprops, name, domains):
    hits = {}
    for d in domains:
        matches = [uri for uri in allprops[d] if local(uri) == name]
        if len(matches) == 1:
            hits[d] = matches[0]
    return hits


# Conservative semantic checks use only property local names and SHACL shape context.
# They are not evidence that a query will return correct instance values.
ROLE_RULES = {
    "engineeringIdentifier": (("engineering", "local", "reference", "identifier"), ("product", "description", "note")),
    "bomItemId": (("item", "id"), ("description", "type", "parent")),
    "sourceDomain": (("source", "domain"), ("description",)),
    "inventoryTag": (("tag",), ("description", "type")),
    "operationalSignal": (("signal", "operational"), ("description", "direction")),
    "manufacturer": (("manufacturer", "name"), ("part", "supplier")),
    "partNumber": (("part", "number"), ("supplier", "description")),
}

def role_issues(field, uri):
    tokens = tokenize(local(uri))
    required, forbidden = ROLE_RULES[field]
    issues = []
    matched = (all(t in tokens for t in required)
               if field in ("bomItemId", "sourceDomain", "partNumber")
               else any(t in tokens for t in required))
    if not matched:
        issues.append("Semantic role mismatch for " + field + ": " + local(uri))
    if any(t in tokens for t in forbidden):
        issues.append("Semantic role conflict for " + field + ": " + local(uri))
    return issues

def shape_context_issues(verified, allprops):
    issues = []
    asset = discover_join(allprops, "hasAssetIdentifier", ASSET_DOMAINS)
    product = discover_join(allprops, "hasProductIdentifier", PRODUCT_DOMAINS)
    join_shapes = {}
    for d, uri in asset.items():
        join_shapes.setdefault(d, set()).add(allprops[d][uri]["shape"])
    for d, uri in product.items():
        join_shapes.setdefault(d, set()).add(allprops[d][uri]["shape"])
    for field in FIELDS:
        if field not in verified:
            continue
        d, uri = verified[field]
        prop_shape = allprops[d][uri]["shape"]
        if prop_shape not in join_shapes.get(d, set()):
            issues.append("Shape mismatch for " + field + ": " + local(uri) +
                          " is declared on a different shape than join predicates; no path established")
    if "filter" in verified:
        d, uri, _ = verified["filter"]
        if allprops[d][uri]["shape"] not in join_shapes.get(d, set()):
            issues.append("Filter property shape does not match join subject shape")
    return issues

def ensure_candidate_coverage(inventory, allprops):
    # Guarantee that role-compatible candidates are included when present.
    # Otherwise a top-k ranking could hide the correct property from the LLM.
    for field, domains in FIELDS.items():
        for d in domains:
            for uri, prop in allprops[d].items():
                if not role_issues(field, uri) and uri not in {p["predicate"] for p in inventory[d]}:
                    inventory[d].append(prop)
    return inventory

def validate_plan(plan, allprops):
    issues = []
    if not isinstance(plan, dict):
        return {}, ["Plan is not an object"]
    if set(plan) != {"fields", "description_filter"}:
        issues.append("Top-level keys must be exactly fields and description_filter")
    fields = plan.get("fields")
    if not isinstance(fields, dict):
        return {}, issues + ["Missing JSON object 'fields'"]
    if set(fields) != set(FIELDS):
        issues.append("Requested-field coverage mismatch: missing=" +
                      repr(sorted(set(FIELDS)-set(fields))) + " extra=" +
                      repr(sorted(set(fields)-set(FIELDS))))
    verified = {}
    unsupported = []
    for field in FIELDS:
        val = fields.get(field)
        if isinstance(val, dict) and val == {"unsupported": True}:
            unsupported.append(field)
            continue
        if not isinstance(val, dict) or set(val) != {"domain", "predicate"}:
            issues.append("Invalid mapping format: " + field)
            continue
        d, uri = val["domain"], val["predicate"]
        if d not in FIELDS[field] or uri not in allprops.get(d, {}):
            issues.append("Undeclared or disallowed SHACL mapping: " + field)
        else:
            issues.extend(role_issues(field, uri))
            verified[field] = (d, uri)
    filt = plan.get("description_filter")
    if filt == {"unsupported": True}:
        issues.append("Description filter unsupported")
    elif not isinstance(filt, dict) or set(filt) != {"domain", "predicate", "text"}:
        issues.append("Invalid description_filter format")
    else:
        d, uri, value = filt["domain"], filt["predicate"], filt["text"]
        if (uri not in allprops.get(d, {}) or
                not any(word in local(uri).lower() for word in DESCRIPTIVE) or
                value != "temperature"):
            issues.append("Invalid or non-descriptive temperature filter")
        else:
            verified["filter"] = (d, uri, value)
    if unsupported:
        issues.append("Unsupported requested fields: " + ", ".join(unsupported))
    issues.extend(shape_context_issues(verified, allprops))
    return verified, issues

def compile_sparql(verified, allprops):
    asset = discover_join(allprops, "hasAssetIdentifier", ASSET_DOMAINS)
    if set(asset) != set(ASSET_DOMAINS):
        raise ValueError("Required asset joins not supported by all five ontologies: " +
                         repr(sorted(set(ASSET_DOMAINS)-set(asset))))
    product = discover_join(allprops, "hasProductIdentifier", PRODUCT_DOMAINS)
    bridge = next((d for d in ("assetinventory", "engineeringbom") if d in product), None)
    if "productcatalog" not in product or not bridge:
        raise ValueError("No ontology-supported ProductIdentifier bridge")
    patterns = ["?s_" + d + " <" + asset[d] + "> ?assetId ." for d in ASSET_DOMAINS]
    patterns.extend(["?s_productcatalog <" + product["productcatalog"] + "> ?productId .",
                     "?s_" + bridge + " <" + product[bridge] + "> ?productId ."])
    vars_ = []
    for f in FIELDS:
        d, uri = verified[f]
        vars_.append("?" + f)
        patterns.append("?s_" + d + " <" + uri + "> ?" + f + " .")
    d, uri, word = verified["filter"]
    patterns.append("?s_" + d + " <" + uri + "> ?descriptionValue .")
    patterns.append("FILTER(CONTAINS(LCASE(STR(?descriptionValue)), " +
                    json.dumps(word) + "))")
    return "SELECT DISTINCT " + " ".join(vars_) + " WHERE {\n  " + "\n  ".join(patterns) + "\n}"

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="qwen2.5-coder:3b")
    ap.add_argument("--question", default=DEFAULT_QUESTION)
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--num-predict", type=int, default=900)
    ap.add_argument("--max-prompt-estimate", type=int, default=4500)
    ap.add_argument("--per-domain", type=int, default=14)
    ap.add_argument("--ollama-timeout", type=int, default=300)
    ap.add_argument("--skip-execution", action="store_true")
    ap.add_argument("--output", default="reports/q13_v8_semantic_plan.json")
    args = ap.parse_args()
    schema = extract()
    inventory, allprops = focused_inventory(schema, args.per_domain)
    inventory = ensure_candidate_coverage(inventory, allprops)
    schemas, allowed = load_ontologies()
    payload = {"question": args.question, "requested_fields": FIELDS,
               "candidate_properties": inventory,
               "integration_policy": {
                   "asset_identifier": "equal RDF terms for hasAssetIdentifier across DEXPI, ECAD, Engineering BOM, AssetInventory, OPC UA",
                   "product_identifier": "equal RDF terms for hasProductIdentifier across ProductCatalog and AssetInventory or Engineering BOM",
                   "status": "explicit experimental policy, not an OWL equivalence axiom"},
               "response_example_shape": {"fields": {
                   name: {"domain": "select_allowed_domain", "predicate": "copy_exact_candidate_IRI"}
                   for name in FIELDS},
                   "description_filter": {"domain": "select_domain", "predicate": "copy_descriptive_IRI", "text": "temperature"}}}
    prompt = json.dumps(payload, separators=(",", ":"))
    estimated = (len(prompt) + len(SYSTEM)) // 4
    path = ROOT / args.output
    if path.exists():
        path = path.with_name(path.stem + "_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + path.suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    report = {"method": "q13_v8_semantic_shape_aware_first_attempt", "question": args.question,
              "model": args.model, "schema_sources": [{"file": x["source_file"], "sha256": x["source_sha256"]} for x in schema["domains"]],
              "selected_candidates": inventory, "estimated_prompt_tokens": estimated,
              "validation_scope": "conservative lexical roles and exact SHACL parent-shape matching; no inference of paths",
              "raw_model_response": None, "plan": None, "plan_issues": [],
              "predicate_issues": [], "structural_validation": None,
              "generated_sparql": None, "time_to_first_token_seconds": None,
              "prompt_eval_count": None, "eval_count": None,
              "prompt_eval_duration_ns": None, "eval_duration_ns": None,
              "total_duration_ns": None, "graphdb_bindings": None,
              "error": None, "completed": False}
    start = time.monotonic()
    try:
        budget = min(args.max_prompt_estimate, args.num_ctx - args.num_predict - 512)
        print("Focused candidates:", sum(map(len, inventory.values())),
              "estimated prompt tokens:", estimated, "budget:", budget, flush=True)
        if estimated > budget:
            raise ValueError("Prompt exceeds estimated budget; reduce --per-domain")
        chunks = []
        final = {}
        with requests.post(args.ollama_url.rstrip("/") + "/api/chat",
            json={"model": args.model, "stream": True, "format": "json",
                  "options": {"temperature": 0, "num_ctx": args.num_ctx,
                              "num_predict": args.num_predict},
                  "messages": [{"role": "system", "content": SYSTEM},
                               {"role": "user", "content": prompt}]},
            timeout=(10, args.ollama_timeout), stream=True) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                event = json.loads(line)
                if event.get("error"):
                    raise RuntimeError(event["error"])
                part = event.get("message", {}).get("content", "")
                if part:
                    if report["time_to_first_token_seconds"] is None:
                        report["time_to_first_token_seconds"] = round(time.monotonic()-start, 2)
                        print("First token at", report["time_to_first_token_seconds"], "seconds", flush=True)
                    chunks.append(part)
                    if len(chunks) % 100 == 0:
                        print("Received", len("".join(chunks)), "characters", flush=True)
                if event.get("done"):
                    report["completed"] = True
                    final = event
                    break
        report["raw_model_response"] = "".join(chunks)
        for key in ("prompt_eval_count", "eval_count"):
            report[key] = final.get(key)
        for key in ("prompt_eval_duration", "eval_duration", "total_duration"):
            report[key + "_ns"] = final.get(key)
        if not report["completed"]:
            raise ValueError("Ollama stream ended without done=true")
        report["plan"] = json.loads(report["raw_model_response"])
        verified, issues = validate_plan(report["plan"], allprops)
        report["plan_issues"] = issues
        if issues:
            print("Plan rejected:", "; ".join(issues), flush=True)
        else:
            query = compile_sparql(verified, allprops)
            report["generated_sparql"] = query
            report["predicate_issues"] = validate_query(query, allowed)
            structure = structural_validation(query)
            report["structural_validation"] = structure
            print("Compiled query:\n", query, flush=True)
            if report["predicate_issues"] or structure.get("issues"):
                print("SPARQL validation failed:", report["predicate_issues"],
                      structure.get("issues"), flush=True)
            elif not args.skip_execution:
                response = requests.post(args.graphdb_url, data={"query": query},
                                         headers={"Accept": "application/sparql-results+json"},
                                         timeout=60)
                response.raise_for_status()
                report["graphdb_bindings"] = response.json()["results"]["bindings"]
                report["evaluation"] = evaluate(report["graphdb_bindings"])
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
        print("ERROR:", report["error"], file=sys.stderr, flush=True)
    finally:
        report["elapsed_seconds"] = round(time.monotonic()-start, 2)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("Audit saved:", path, flush=True)
    return int(bool(report["error"] or report["plan_issues"] or report["predicate_issues"] or
                    (report["structural_validation"] or {}).get("issues") or not report["completed"]))

if __name__ == "__main__":
    sys.exit(main())
