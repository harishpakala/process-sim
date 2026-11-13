#!/usr/bin/env python3
"""Q13-v10: focused ontology-only SHACL retrieval, strict JSON planning, deterministic SPARQL.

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
from q13_v4_compact_shacl_ab import ROOT, load_ontologies, validate_query

QUESTION = ("Trace the reactor temperature measurement across DEXPI, ECAD, "
            "AssetInventory, OPC UA Connectivity, and ProductCatalog. Return engineering "
            "identifiers, inventory equipment tag, operational signal, manufacturer, and "
            "manufacturer part number. Identify the measurement using ontology-supported "
            "descriptions rather than assuming its identifier.")
FIELDS = {
    "engineeringIdentifier": ["dexpi", "ecad"],
    "inventoryTag": ["assetinventory"],
    "operationalSignal": ["opcuaconnectivity", "assetinventory"],
    "manufacturer": ["productcatalog"],
    "partNumber": ["productcatalog"],
}
ASSET_DOMAINS = ["dexpi", "ecad", "assetinventory", "opcuaconnectivity"]
PRODUCT_DOMAINS = ["productcatalog", "assetinventory"]
ALIASES = {
    "engineeringIdentifier": ["engineering", "identifier", "reference", "tag"],
    "inventoryTag": ["inventory", "tag", "name"],
    "operationalSignal": ["operational", "signal", "reference", "node"],
    "manufacturer": ["manufacturer", "brand"],
    "partNumber": ["part", "number", "model"],
}
ACTIVE_DOMAINS = set(ASSET_DOMAINS + ["productcatalog"])
DESCRIPTIVE = ("name", "description", "label", "designation", "measuredvariable", "measurement")
SYSTEM = """Each field has its own field_candidates list. Select ONLY from the matching field list, never from another field. If empty, mark unsupported. Select the description filter ONLY from description_candidates.
Only select properties whose names and labels semantically express the requested output. A product identifier is NOT an engineering identifier. A property must also be on a SHACL shape compatible with the domain identifier join. If no matching predicate is available, mark the field unsupported.\nYou select SHACL property IRIs for a fixed engineering question. Do NOT write SPARQL.
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
        if d not in ACTIVE_DOMAINS:
            continue
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
        if d in ("dexpi", "ecad"):
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
               if field == "partNumber"
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

def field_candidates(allprops):
    """Whitelist by semantic role and SHACL identifier-bearing parent shape."""
    asset = discover_join(allprops, "hasAssetIdentifier", ASSET_DOMAINS)
    product = discover_join(allprops, "hasProductIdentifier", PRODUCT_DOMAINS)
    result = {}
    for field, domains in FIELDS.items():
        matches = []
        for domain in domains:
            join_uris = [u for u in (asset.get(domain), product.get(domain)) if u]
            shapes = {allprops[domain][u]["shape"] for u in join_uris}
            for uri, prop in allprops[domain].items():
                if not role_issues(field, uri) and prop["shape"] in shapes:
                    matches.append({"domain": domain, "predicate": uri,
                                    "label": prop["label"], "shape": prop["shape"]})
        result[field] = sorted(matches, key=lambda p: (p["domain"], p["predicate"]))
    return result

def filter_candidates(allprops):
    asset = discover_join(allprops, "hasAssetIdentifier", ASSET_DOMAINS)
    result = []
    for domain, join_uri in asset.items():
        shape = allprops[domain][join_uri]["shape"]
        for uri, prop in allprops[domain].items():
            if (prop["shape"] == shape and
                    any(x in local(uri).lower() for x in DESCRIPTIVE) and
                    prop.get("kind") != "object"):
                result.append({"domain": domain, "predicate": uri,
                               "label": prop["label"], "shape": prop["shape"]})
    return sorted(result, key=lambda p: (p["domain"], p["predicate"]))

def validate_plan(plan, allprops, candidates=None, descriptions=None):
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
            if candidates is not None and (d, uri) not in {(p["domain"], p["predicate"]) for p in candidates[field]}:
                issues.append("Field mapping outside semantic candidate whitelist: " + field)
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
            if descriptions is not None and (d, uri) not in {(p["domain"], p["predicate"]) for p in descriptions}:
                issues.append("Description filter outside candidate whitelist")
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
    bridge = next((d for d in ("assetinventory",) if d in product), None)
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

def five_domain_structure(query):
    """Basic structural checks independent of the six-domain Q13 validator."""
    from rdflib.plugins.sparql.parser import parseQuery
    parseQuery(query)
    required = ["https://example.org/" + d + "/hasAssetIdentifier"
                for d in ASSET_DOMAINS]
    required += ["https://example.org/productcatalog/hasProductIdentifier",
                 "https://example.org/assetinventory/hasProductIdentifier"]
    missing = [uri for uri in required if "<" + uri + ">" not in query]
    if "engineeringbom/" in query.lower():
        missing.append("Unexpected Engineering BOM predicate")
    return {"domains_present": sorted(ACTIVE_DOMAINS),
            "domains_missing": [],
            "issues": ["Missing join predicate: " + x for x in missing]}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="qwen2.5-coder:3b")
    ap.add_argument("--question", default=QUESTION)
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--num-predict", type=int, default=900)
    ap.add_argument("--max-prompt-estimate", type=int, default=4500)
    ap.add_argument("--per-domain", type=int, default=14)
    ap.add_argument("--ollama-timeout", type=int, default=300)
    ap.add_argument("--skip-execution", action="store_true")
    ap.add_argument("--output", default="reports/q13_v10_five_domains.json")
    args = ap.parse_args()
    schema = extract()
    schema["domains"] = [d for d in schema["domains"] if d["domain"] in ACTIVE_DOMAINS]
    inventory, allprops = focused_inventory(schema, args.per_domain)
    candidates = field_candidates(allprops)
    descriptions = filter_candidates(allprops)
    schemas, allowed = load_ontologies()
    payload = {"question": args.question, "requested_fields": FIELDS,
               "field_candidates": candidates, "description_candidates": descriptions,
               "integration_policy": {
                   "asset_identifier": "equal RDF terms for hasAssetIdentifier across DEXPI, ECAD, AssetInventory, OPC UA",
                   "product_identifier": "equal RDF terms for hasProductIdentifier across ProductCatalog and AssetInventory",
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
    report = {"excluded_domains": ["engineeringbom"], "method": "q13_v10_five_domains_first_attempt", "question": args.question,
              "model": args.model, "schema_sources": [{"file": x["source_file"], "sha256": x["source_sha256"]} for x in schema["domains"]],
              "selected_candidates": candidates, "description_candidates": descriptions,
              "missing_candidate_fields": [f for f, items in candidates.items() if not items],
              "estimated_prompt_tokens": estimated,
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
        print("Active domains:", ", ".join(sorted(ACTIVE_DOMAINS)), flush=True)
        print("Field candidates:", sum(map(len, candidates.values())),
              "description candidates:", len(descriptions),
              "missing:", report["missing_candidate_fields"],
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
        verified, issues = validate_plan(report["plan"], allprops, candidates, descriptions)
        report["plan_issues"] = issues
        report["unsupported_fields"] = [f for f, v in report["plan"].get("fields", {}).items() if v == {"unsupported": True}]
        if issues:
            print("Plan rejected:", "; ".join(issues), flush=True)
        else:
            query = compile_sparql(verified, allprops)
            report["generated_sparql"] = query
            report["predicate_issues"] = validate_query(query, allowed)
            structure = five_domain_structure(query)
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
                report["binding_count"] = len(report["graphdb_bindings"])
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
