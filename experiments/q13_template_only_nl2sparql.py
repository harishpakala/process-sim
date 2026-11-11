#!/usr/bin/env python3
"""Q13 ontology-only natural-language to SPARQL experiment.

Ollama sees ONLY the natural-language question, six template-derived TTL files,
and generic query-generation instructions. No instance evidence, reference
SPARQL, expected identifiers, or expected bindings enter the model prompt.

Run from repository root:
  python experiments/q13_template_only_nl2sparql.py \
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
from pathlib import Path

import requests
from rdflib import Graph, URIRef
from rdflib.plugins.sparql.parser import parseQuery

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
SYSTEM = """You are a SPARQL 1.1 query author for an engineering RDF graph.
You receive a natural-language question and six AAS template-derived TTL schemas.
Use ONLY the supplied schemas to identify valid predicates and join paths.
Generate ONE complete read-only SPARQL SELECT query against instance data.
Derive cross-domain joins independently; never assume an identifier value,
product, signal, BOM item, or expected answer not stated in the question.
The templates are schema constraints, NOT instance facts.
All domain identifiers may be represented as RDF literals; join variables
on matching RDF terms rather than treating literal identifier strings as IRIs.
For identifying the requested measurement, use graph values (e.g. names,
descriptions or local IDs) and case-insensitive text matching where the
schema permits. Do not invent predicates or relationships.
Do not include INSERT, DELETE, UPDATE, LOAD, SERVICE, or other side effects.
Return ONLY a JSON object with keys "sparql" and "rationale".
No markdown fences. If insufficient schema information, still give your best
query and explain the limitation in rationale. Do not use a reference query."""

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
    r"\\b(?:INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|MOVE|COPY|ADD|"
    r"WITH|USING|SERVICE|DESCRIBE|CONSTRUCT|ASK)\\b",
    re.IGNORECASE,
)
IRI_TOKEN = re.compile(r"<([^>]+)>")
PREFIX = re.compile(r"\\bPREFIX\\s+([\\w-]*):\\s*<([^>]+)>", re.IGNORECASE)
PREDICATE = re.compile(r"(?<![\\w:])([A-Za-z][\\w-]*):([A-Za-z_][\\w.-]*)")


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
    from rdflib.namespace import SH
    allowed = {str(obj) for obj in graph.objects(None, SH.path) if isinstance(obj, URIRef)}
    return schemas, allowed


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
    clean = re.sub(r"#[^\\n]*", "", query)
    clean = re.sub(r'"(?:\\\\.|[^"\\\\])*"|\'(?:\\\\.|[^\'\\\\])*\'', '""', clean)
    if FORBIDDEN.search(clean):
        issues.append("Forbidden non-SELECT keyword or remote SERVICE detected.")
    if not re.search(r"\\bSELECT\\b", clean, re.IGNORECASE):
        issues.append("Query must contain SELECT.")
    if re.search(r"\\b(?:FROM|GRAPH)\\s*<", clean, re.IGNORECASE):
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
    p.add_argument("--graphdb-timeout", type=int, default=60)
    p.add_argument("--output", default="reports/q13_template_only_nl2sparql.json")
    p.add_argument("--skip-execution", action="store_true",
                   help="Generate and validate SPARQL without contacting GraphDB.")
    args = p.parse_args()
    schemas, allowed = load_ontologies()
    prompt = {
        "question": args.question,
        "ontologies": [{"filename": s["file"], "turtle": s["ttl"]} for s in schemas],
    }
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
    ]
    audit = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "ontology_only_first_attempt_nl2sparql",
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
        "graphdb_bindings": None,
        "evaluation": None,
        "error": None,
        "first_attempt_only": True,
    }
    destination = ROOT / args.output
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        print("Sending six template TTL ontologies and question to Ollama...", flush=True)
        response = requests.post(
            args.ollama_url.rstrip("/") + "/api/chat",
            json={"model": args.model, "messages": messages,
                  "stream": False, "format": "json",
                  "options": {"temperature": 0}},
            timeout=args.ollama_timeout,
        )
        response.raise_for_status()
        query, rationale, raw = extract_sparql(response.json())
        audit["generated_sparql"] = query
        audit["model_rationale"] = rationale
        audit["raw_model_response"] = raw
        issues = validate_query(query, allowed)
        audit["syntax_and_schema_issues"] = issues
        print("Generated SPARQL:\\n" + (query or "<none>"), flush=True)
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
                               + "\\n", encoding="utf-8")
        print("Audit saved: " + str(destination), flush=True)
    return 1 if audit["error"] or audit["syntax_and_schema_issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
