#!/usr/bin/env python3
"""Q13-v3 complete SHACL/OWL A/B ontology-only natural-language to SPARQL experiment.

Ollama sees ONLY the natural-language question and schema derived from six TTL files,
and generic query-generation instructions. No instance evidence, reference
SPARQL, expected identifiers, or expected bindings enter the model prompt.

Run from repository root:
  python experiments/q13_v3_full_shacl_ab.py \
    --graphdb-url http://localhost:7200/repositories/AAS \
    --ollama-url http://localhost:11434 --model llama3.1:8b

Requires: requests, rdflib. No TimescaleDB dependency. Does not lift/rewrite TTL.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from q13_extract_focused_schema import extract as extract_focused_schema
from pathlib import Path

import requests
from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS, SH, OWL
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.algebra import translateQuery
from rdflib.plugins.sparql.parserutils import CompValue
from rdflib.term import Variable

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_DIR = ROOT / "semantic" / "ontology"
FILES = (
    "dexpi-template.ttl",
    "ecad-template.ttl",
    "engineeringbom-template.ttl",
    "assetinventory-template.ttl",
    "opcuaconnectivity-template.ttl",
    "productcatalog-template.ttl",
)
DEFAULT_QUESTION = (
    "Trace the reactor temperature measurement across DEXPI, ECAD, "
    "Engineering BOM, AssetInventory, OPC UA Connectivity, and ProductCatalog. "
    "Return the engineering identifiers, BOM item IDs and source domains, "
    "inventory tag, operational signal, manufacturer, and part number. "
    "Find the relevant measurement using the available graph descriptions "
    "or labels rather than assuming its identifier."
)
SYSTEM = """You generate one read-only SPARQL 1.1 SELECT query using only the
provided complete OWL/SHACL Turtle ontologies. Select exact predicate IRIs
declared as SHACL sh:path, not invented property names. A prefixed predicate
is prefix:property, never ?prefix:property. Use the ontology's class and shape
constraints to construct graph patterns. Identify the requested measurement
through descriptive text, not by regex on opaque identifiers. Do not assume
instance facts, answer values, or a reference query. Return ONLY a JSON object
with keys sparql and rationale; no markdown."""
JOIN_METADATA = {
    "status": "explicit experiment integration policy; value-equality joins, NOT OWL equivalence axioms",
    "asset_identifier": {
        "domains": ["dexpi", "ecad", "engineeringbom", "assetinventory", "opcuaconnectivity"],
        "rule": "Require a mandatory hasAssetIdentifier triple in each domain, all using one shared identifier-value variable."
    },
    "product_identifier": {
        "domains": ["productcatalog", "assetinventory", "engineeringbom"],
        "rule": "Require ProductCatalog hasProductIdentifier to share one value variable with hasProductIdentifier on AssetInventory or Engineering BOM."
    },
    "required": "All six domains contribute mandatory triples. Do not place mandatory identifier joins solely in OPTIONAL or UNION."
}


# Post-execution evaluation only. NEVER include this object in Ollama messages.
REFERENCE = {
    "asset_identifier": "https://aas.example.com/TI101",
    "bom_item_ids": ["EBOM-0016", "EBOM-0050"],
    "signal": "XMEAS9",
    "manufacturer": "IFM",
    "part_number": "TA1101",
    "product_identifier": "https://example.org/product-types/IFM_TA1101",
}
FORBIDDEN = re.compile(
    r"\b(?:INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|MOVE|COPY|ADD|"
    r"WITH|USING|SERVICE|DESCRIBE|CONSTRUCT|ASK)\b",
    re.IGNORECASE,
)
IRI_TOKEN = re.compile(r"<([^>]+)>")
PREFIX = re.compile(r"\bPREFIX\s+([\w-]*):\s*<([^>]+)>", re.IGNORECASE)
PREDICATE = re.compile(r"(?<![\w:])([A-Za-z][\w-]*):([A-Za-z_][\w.-]*)")


def load_ontologies():
    graph = Graph()
    schemas = []
    for filename in FILES:
        path = ONTOLOGY_DIR / filename
        data = path.read_text(encoding="utf-8")
        graph.parse(data=data, format="turtle")
        schemas.append({
            "file": filename,
            "sha256": hashlib.sha256(data.encode("utf-8")).hexdigest(),
            "ttl": data,
        })
    allowed = {str(obj) for obj in graph.objects(None, SH.path) if isinstance(obj, URIRef)}
    return schemas, allowed



def compact_schema(schemas):
    """Extract schema-only SHACL paths and their parent shapes, never instance data."""
    domains = []
    for item in schemas:
        graph = Graph()
        graph.parse(data=item["ttl"], format="turtle")
        paths = {}
        for shape in graph.subjects(SH.path, None):
            path = graph.value(shape, SH.path)
            if not isinstance(path, URIRef):
                continue
            entry = paths.setdefault(str(path), {"uri": str(path), "labels": set(),
                                                  "contexts": set(), "kind": set()})
            label = graph.value(shape, RDFS.label)
            if label:
                entry["labels"].add(str(label))
            for node in graph.subjects(SH.property, shape):
                context = graph.value(node, RDFS.label)
                if context:
                    entry["contexts"].add(str(context))
            for kind in (OWL.ObjectProperty, OWL.DatatypeProperty):
                if (path, RDF.type, kind) in graph:
                    entry["kind"].add("object" if kind == OWL.ObjectProperty else "datatype")
        domains.append({
            "filename": item["file"],
            "properties": [
                {"uri": entry["uri"], "labels": sorted(entry["labels"]),
                 "parent_shapes": sorted(entry["contexts"]), "kind": sorted(entry["kind"])}
                for _, entry in sorted(paths.items())
            ],
        })
    return domains


def estimate_tokens(text):
    """Approximation; actual token usage comes from Ollama."""
    return (len(text) + 3) // 4


def extract_sparql(response):
    payload = response.get("message", {}).get("content", "")
    try:
        obj = json.loads(payload)
        if isinstance(obj, dict) and isinstance(obj.get("sparql"), str):
            return obj["sparql"].strip(), obj.get("rationale", ""), payload
    except json.JSONDecodeError:
        pass
    # Preserve original model response even when JSON parsing fails.
    return "", "", payload


def validate_query(query, allowed_predicates):
    issues = []
    if not query:
        return ["No SPARQL query in Ollama JSON response."]
    clean = re.sub(r"#[^\n]*", "", query)
    clean = re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', '""', clean)
    if FORBIDDEN.search(clean):
        issues.append("Forbidden non-SELECT keyword or remote SERVICE detected.")
    if not re.search(r"\bSELECT\b", clean, re.IGNORECASE):
        issues.append("Query must contain SELECT.")
    if re.search(r"\b(?:FROM|GRAPH)\s*<", clean, re.IGNORECASE):
        issues.append("Explicit graph/dataset targeting is disabled in this experiment.")
    try:
        parseQuery(query)
    except Exception as exc:
        issues.append("SPARQL parser error: " + str(exc))
    namespaces = dict(PREFIX.findall(query))
    standard = {"rdf", "rdfs", "owl", "xsd", "sh"}
    unknown = set()
    # Identify domain-prefixed terms that appear as triple predicates.
    for prefix, local in PREDICATE.findall(clean):
        if prefix in standard or prefix not in namespaces:
            continue
        uri = namespaces[prefix] + local
        if namespaces[prefix].startswith("https://example.org/") and uri not in allowed_predicates:
            unknown.add(uri)
    if unknown:
        issues.append("Predicates absent from supplied SHACL sh:path declarations: "
                      + ", ".join(sorted(unknown)))
    return issues


def structural_validation(query):
    """Validate mandatory six-domain identifier joins without repairing the query.

    OPTIONAL right branches and UNION alternatives are not sufficient evidence
    of required joins. This deliberately conservative check can reject valid
    queries with equivalent but differently structured joins.
    """
    required = {
        "dexpi": "https://example.org/dexpi/",
        "ecad": "https://example.org/ecad/",
        "engineeringbom": "https://example.org/engineeringbom/",
        "assetinventory": "https://example.org/assetinventory/",
        "opcuaconnectivity": "https://example.org/opcuaconnectivity/",
        "productcatalog": "https://example.org/productcatalog/",
    }
    asset_domains = set(required) - {"productcatalog"}
    asset_predicates = {name: ns + "hasAssetIdentifier"
                        for name, ns in required.items() if name in asset_domains}
    product_predicates = {
        name: required[name] + "hasProductIdentifier"
        for name in ("engineeringbom", "assetinventory", "productcatalog")
    }
    result = {
        "domains_present": [], "domains_missing": [],
        "triple_count": 0, "connected": False,
        "shared_identifier_variables": [],
        "asset_identifier_variable": None, "product_identifier_variable": None,
        "asset_join_domains": [], "product_bridge_domains": [], "issues": [],
    }
    try:
        algebra = translateQuery(parseQuery(query)).algebra
    except Exception as exc:
        result["issues"].append("Cannot inspect SPARQL algebra: " + str(exc))
        return result

    triples = []
    def walk(node):
        if not isinstance(node, CompValue):
            return
        if node.name == "BGP":
            triples.extend(node.get("triples", []))
            return
        if node.name == "LeftJoin":
            walk(node.get("p1"))  # OPTIONAL right side is not mandatory
            return
        if node.name in ("Union", "Minus"):
            if node.name == "Minus":
                walk(node.get("p1"))
            # UNION branches are alternatives, not guaranteed shared joins.
            return
        for value in node.values():
            if isinstance(value, CompValue):
                walk(value)
            elif isinstance(value, (tuple, list)):
                for child in value:
                    walk(child)

    walk(algebra)
    result["triple_count"] = len(triples)
    present, edges = set(), {}
    asset_usage, product_usage = {}, {}
    for subject, predicate, obj in triples:
        if isinstance(predicate, URIRef):
            uri = str(predicate)
            for name, ns in required.items():
                if uri.startswith(ns):
                    present.add(name)
            if isinstance(obj, Variable):
                for name, expected in asset_predicates.items():
                    if uri == expected:
                        asset_usage.setdefault(str(obj), set()).add(name)
                for name, expected in product_predicates.items():
                    if uri == expected:
                        product_usage.setdefault(str(obj), set()).add(name)
        for term in (subject, obj):
            if isinstance(term, Variable):
                edges.setdefault(str(term), set())
        if isinstance(subject, Variable) and isinstance(obj, Variable):
            edges[str(subject)].add(str(obj))
            edges[str(obj)].add(str(subject))

    result["domains_present"] = sorted(present)
    result["domains_missing"] = sorted(set(required) - present)
    result["shared_identifier_variables"] = sorted(
        set(var for var, domains in asset_usage.items() if len(domains) > 1)
        | set(var for var, domains in product_usage.items() if len(domains) > 1)
    )
    asset_matches = sorted(var for var, domains in asset_usage.items()
                           if asset_domains <= domains)
    if asset_matches:
        result["asset_identifier_variable"] = asset_matches[0]
        result["asset_join_domains"] = sorted(asset_domains)
    else:
        result["asset_join_domains"] = sorted(
            max(asset_usage.values(), key=len, default=set())
        )
        result["issues"].append(
            "No single mandatory AssetIdentifier variable joins DEXPI, ECAD, "
            "Engineering BOM, AssetInventory, and OPC UA Connectivity."
        )
    bridge_matches = sorted(
        (var, domains) for var, domains in product_usage.items()
        if "productcatalog" in domains
        and domains & {"assetinventory", "engineeringbom"}
    )
    if bridge_matches:
        result["product_identifier_variable"] = bridge_matches[0][0]
        result["product_bridge_domains"] = sorted(bridge_matches[0][1])
    else:
        result["issues"].append(
            "No mandatory ProductIdentifier variable joins ProductCatalog "
            "to AssetInventory or Engineering BOM."
        )
    if result["domains_missing"]:
        result["issues"].append("Missing mandatory domain triple patterns: " +
                                ", ".join(result["domains_missing"]))
    if edges:
        visited = {next(iter(edges))}
        pending = list(visited)
        while pending:
            for neighbor in edges[pending.pop()]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        result["connected"] = visited == set(edges)
    if not result["connected"]:
        result["issues"].append("Disconnected mandatory graph-pattern variables.")
    return result


def evaluate(bindings):
    """Descriptive evaluation only: never alter query or fill missing results."""
    values = [{key: cell.get("value") for key, cell in row.items()}
              for row in bindings]
    def contains(target):
        return any(target in row.values() for row in values)
    bom_found = sorted({v for row in values for v in row.values()
                        if v in REFERENCE["bom_item_ids"]})
    return {
        "row_count": len(values),
        "expected_row_count": 2,
        "exact_row_count": len(values) == 2,
        "expected_bom_items_found": bom_found,
        "both_expected_bom_items_found": bom_found == REFERENCE["bom_item_ids"],
        "asset_identifier_found": contains(REFERENCE["asset_identifier"]),
        "signal_found": contains(REFERENCE["signal"]),
        "manufacturer_found": contains(REFERENCE["manufacturer"]),
        "part_number_found": contains(REFERENCE["part_number"]),
        "product_identifier_found": contains(REFERENCE["product_identifier"]),
        "note": "Field-presence checks are diagnostic, not proof that joins are "
                "semantically correct. Manually inspect all returned bindings.",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    p.add_argument("--ollama-url", default="http://localhost:11434")
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--question", default=DEFAULT_QUESTION)
    p.add_argument("--ollama-timeout", type=int, default=300)
    p.add_argument("--num-ctx", type=int, default=16384)
    p.add_argument("--variant", choices=("a", "b"), required=True,
                   help="a=full OWL/SHACL only; b=same plus explicit join metadata")
    p.add_argument("--num-predict", type=int, default=1800)
    p.add_argument("--graphdb-timeout", type=int, default=60)
    p.add_argument("--output", default=None)
    p.add_argument("--skip-execution", action="store_true",
                   help="Generate and validate SPARQL without contacting GraphDB.")
    args = p.parse_args()
    schemas, allowed = load_ontologies()
    ontology_input = [{"filename": item["file"], "turtle": item["ttl"]}
                      for item in schemas]
    prompt = {"question": args.question, "ontologies": ontology_input}
    if args.variant == "b":
        prompt["cross_domain_join_metadata"] = JOIN_METADATA
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
    ]
    prompt_text = json.dumps(prompt, ensure_ascii=False)
    audit = {
        "variant": args.variant,
        "requested_num_predict": args.num_predict,
        "requested_num_ctx": args.num_ctx,
        "prompt_chars": len(SYSTEM) + len(prompt_text),
        "estimated_prompt_tokens": estimate_tokens(SYSTEM + prompt_text),
        "actual_prompt_tokens": None,
        "actual_generated_tokens": None,
        "prompt_eval_duration_ns": None,
        "eval_duration_ns": None,
        "total_duration_ns": None,
        "generation_tokens_per_second": None,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "q13_v3_full_shacl_ab_first_attempt_nl2sparql",
        "schema_representation": "complete_six_owl_shacl_ttl" + ("_plus_explicit_join_policy" if args.variant == "b" else "_only"),
        "question": args.question,
        "model": args.model,
        "ontology_files": [{"file": s["file"], "sha256": s["sha256"]}
                           for s in schemas],
        "prompt_system": SYSTEM,
        "prompt_user": prompt,
        "generated_sparql": None,
        "model_rationale": None,
        "raw_model_response": None,
        "syntax_and_schema_issues": [],
        "structural_validation": None,
        "graphdb_bindings": None,
        "evaluation": None,
        "error": None,
        "first_attempt_only": True,
    }
    destination = ROOT / (args.output or f"reports/q13_v3{args.variant}_full_shacl.json")
    if not destination.is_absolute():
        destination = ROOT / destination
    if destination.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = destination.with_name(destination.stem + "_" + stamp + destination.suffix)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        print("Sending six complete OWL/SHACL ontologies to Ollama: variant", args.variant,
              "estimated tokens:", audit["estimated_prompt_tokens"],
              "num_ctx:", args.num_ctx, flush=True)
        response = requests.post(
            args.ollama_url.rstrip("/") + "/api/chat",
            json={"model": args.model, "messages": messages,
                  "stream": False,
                  "format": {"type": "object", "properties": {
                      "sparql": {"type": "string"},
                      "rationale": {"type": "string"}},
                      "required": ["sparql", "rationale"],
                      "additionalProperties": False},
                  "options": {"temperature": 0, "num_ctx": args.num_ctx,
                              "num_predict": args.num_predict}},
            timeout=args.ollama_timeout,
        )
        response.raise_for_status()
        model_response = response.json()
        audit["actual_prompt_tokens"] = model_response.get("prompt_eval_count")
        audit["actual_generated_tokens"] = model_response.get("eval_count")
        for key in ("prompt_eval_duration", "eval_duration", "total_duration"):
            audit[key + "_ns"] = model_response.get(key)
        if model_response.get("eval_duration") and model_response.get("eval_count") is not None:
            audit["generation_tokens_per_second"] = round(
                model_response["eval_count"] * 1e9 / model_response["eval_duration"], 2)
        query, rationale, raw = extract_sparql(model_response)
        audit["generated_sparql"] = query
        audit["model_rationale"] = rationale
        audit["raw_model_response"] = raw
        issues = validate_query(query, allowed)
        structure = structural_validation(query) if query else None
        audit["structural_validation"] = structure
        if structure:
            issues.extend(structure["issues"])
        audit["syntax_and_schema_issues"] = issues
        print("Ollama prompt tokens:", audit["actual_prompt_tokens"],
              "generated tokens:", audit["actual_generated_tokens"],
              "tokens/sec:", audit["generation_tokens_per_second"], flush=True)
        print("Generated SPARQL:\n" + (query or "<none>"), flush=True)
        if issues:
            print("Validation failed; query will NOT execute: " + "; ".join(issues),
                  flush=True)
        elif not args.skip_execution:
            print("Executing unchanged generated SELECT in GraphDB...", flush=True)
            result = requests.post(
                args.graphdb_url,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"},
                timeout=args.graphdb_timeout,
            )
            result.raise_for_status()
            bindings = result.json()["results"]["bindings"]
            audit["graphdb_bindings"] = bindings
            audit["evaluation"] = evaluate(bindings)
            print("Returned " + str(len(bindings)) + " bindings.", flush=True)
    except Exception as exc:
        audit["error"] = type(exc).__name__ + ": " + str(exc)
        print("ERROR: " + audit["error"], file=sys.stderr, flush=True)
    finally:
        destination.write_text(json.dumps(audit, indent=2, ensure_ascii=False)
                               + "\n", encoding="utf-8")
        print("Audit saved: " + str(destination), flush=True)
    return 1 if audit["error"] or audit["syntax_and_schema_issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
