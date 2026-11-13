#!/usr/bin/env python3
"""Catalog-driven EBOM V2 SPARQL compiler with graph-grounded entity resolution.

Supported vertical slice: DEXPI instrumentation functional associations.
The catalog selects predicates and directions; it is not an unrestricted NL planner.
"""
import argparse
import json
import re
from pathlib import Path
from rdflib.plugins.sparql.parser import parseQuery
from dtwise_entity_resolver import normalize_tag, resolve_remote, resolve_local
from dtwise_path_selector import load_catalog, select_path
from ebom_v2_nl2sparql import parse_intent, run_query

DEFAULT_ENDPOINT = "http://localhost:7200/repositories/AAS"
ROOT = Path(__file__).resolve().parents[1]

def compile_query(plan, catalog, resolved=None):
    intent_name = plan["intent"]
    intent = catalog["intents"][intent_name]
    path = select_path(catalog, intent_name)
    graph_uri = catalog["graph"]
    if not re.fullmatch(r"https?://[^\s<>\"{}|^\\\\]+", graph_uri):
        raise ValueError("INVALID_GRAPH_URI")
    tag = normalize_tag(plan["equipment_tag"])
    prefixes = "\n".join(f"PREFIX {k}: <{v}>" for k,v in sorted(catalog["prefixes"].items()))
    lines = [f"?{intent['start']} a {catalog['nodes'][intent['start']]['rdf_type']} ."]
    if resolved:
        # Bind the exact verified equipment and assembly IRIs, never a fabricated alias.
        for node_name, key in (("equipment", "equipment_uri"), ("assembly", "assembly_uri")):
            value = resolved[key]
            if not re.fullmatch(r"https?://[^\s<>\"{}|^\\\\]+", value):
                raise ValueError("INVALID_RESOLVED_IRI")
            lines.append(f"VALUES ?{node_name} {{ <{value}> }}")
    lines.append(f"?equipment ebom:hasEngineeringLocalId {json.dumps(tag)} .")
    for edge in path:
        source, target = edge["from"], edge["to"]
        lines.append(f"?{target} a {catalog['nodes'][target]['rdf_type']} .")
        if edge["direction"] == "forward":
            lines.append(f"?{source} {edge['predicate']} ?{target} .")
        else:
            lines.append(f"?{target} {edge['predicate']} ?{source} .")
    for flt in intent["required_filters"]:
        lines.append(f"?{flt['node']} {flt['predicate']} {json.dumps(flt['value'])} .")
    for evidence in intent["required_evidence"]:
        variable = "evidence_" + str(len(lines))
        lines.append(f"?{evidence['node']} {evidence['predicate']} ?{variable} .")
    fields = intent["outputs"]
    if set(plan["outputs"]) != set(fields):
        raise ValueError("UNSUPPORTED_OUTPUTS")
    for name, field in fields.items():
        lines.append(f"?{field['node']} {field['predicate']} ?{name} .")
    variables = " ".join("?" + name for name in plan["outputs"])
    body = "\n    ".join(lines)
    query = f"{prefixes}\nSELECT DISTINCT {variables} WHERE {{\n  GRAPH <{graph_uri}> {{\n    {body}\n  }}\n}}\nORDER BY ?engineeringId"
    parseQuery(query)
    return query

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--question", required=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    p.add_argument("--catalog", type=Path)
    p.add_argument("--local-ttl", type=Path, help="Resolve identity against local RDF instead of GraphDB")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    try:
        plan = parse_intent(args.question)
        catalog = load_catalog(args.catalog) if args.catalog else load_catalog()
        if args.local_ttl:
            from rdflib import Graph
            resolved = resolve_local(Graph().parse(args.local_ttl, format="turtle"), plan["equipment_tag"])
        elif args.execute:
            resolved = resolve_remote(plan["equipment_tag"], args.endpoint, catalog["graph"])
        else:
            resolved = None
        query = compile_query(plan, catalog, resolved)
        result = {"status": "compiled", "plan": plan, "path": [e["id"] for e in select_path(catalog, plan["intent"])],
                  "resolution": resolved, "sparql": query}
        if args.execute:
            bindings = run_query(query, args.endpoint)["results"]["bindings"]
            result.update(status="executed", binding_count=len(bindings), results=bindings)
    except ValueError as e:
        result = {"status": "unsupported", "reason": str(e)}
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if result["status"] == "unsupported":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
