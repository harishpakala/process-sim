#!/usr/bin/env python3
"""Phase 3: evidence-preserving, catalog-driven functional association queries.

Supports ALL, ECAD Devices, DEXPI ActuatingFunctions, and DEXPI
InstrumentationFunctions. Does not infer physical membership.
"""
import argparse
import json
import re
from pathlib import Path
from rdflib.plugins.sparql.parser import parseQuery
from dtwise_entity_resolver import normalize_tag, resolve_remote
from dtwise_path_selector import load_catalog, select_path
from ebom_v2_nl2sparql import run_query

DEFAULT_ENDPOINT = "http://localhost:7200/repositories/AAS"
TAG_RE = re.compile(r"\b[A-Za-z]{1,6}[-_][0-9]{1,8}\b")
ALLOWED = set("""which what list show give me all the engineering items item devices device
functions function are is functionally associated association associations with to of for
equipment tag reactor condenser compressor separator stripper return their identifiers
identifier ids id descriptions description and asset from ebom bom according as in v2
please dexpi ecad instrumentation instruments instrument actuating""".split())
BANNED = re.compile(r"\b(physically|installed|mounted|contained|parts|components|procurement|quantity|opc|historical|temporal|timeseries|catalog|inventory)\b")

def parse_question(question):
    q = question.lower()
    if BANNED.search(q):
        raise ValueError("UNSUPPORTED_RELATION_OR_DOMAIN")
    if not re.search(r"functionally associated|functional associations?\b", q):
        raise ValueError("UNSUPPORTED_INTENT: functional association required")
    tags = sorted({normalize_tag(m.group()) for m in TAG_RE.finditer(question)})
    if len(tags) != 1:
        raise ValueError("AMBIGUOUS_ENTITY: exactly one explicit equipment tag required")
    unknown = set(re.findall(r"[a-z][a-z0-9]*", TAG_RE.sub(" ", q))) - ALLOWED
    if unknown:
        raise ValueError("UNSUPPORTED_TERMS: " + ", ".join(sorted(unknown)))
    dexpi, ecad = bool(re.search(r"\bdexpi\b", q)), bool(re.search(r"\becad\b", q))
    instrumentation = bool(re.search(r"\binstrumentation\b|\binstruments?\b", q))
    actuating = bool(re.search(r"\bactuating\b", q))
    devices = bool(re.search(r"\bdevices?\b", q))
    if sum((dexpi, ecad)) > 1 or sum((instrumentation, actuating, devices)) > 1:
        raise ValueError("AMBIGUOUS_FILTER")
    if dexpi and instrumentation:
        intent = "dexpi_instrumentation_phase3"
    elif dexpi and actuating:
        intent = "dexpi_actuating_functional_association"
    elif ecad and devices:
        intent = "ecad_devices_functional_association"
    elif not (dexpi or ecad or instrumentation or actuating or devices):
        intent = "all_functional_associations"
    else:
        raise ValueError("UNSUPPORTED_FILTER_COMBINATION")
    return {"intent": intent, "equipment_tag": tags[0],
            "outputs": ["engineeringId", "description", "sourceDomain", "sourceGroup"]}

def compile_query(plan, catalog, resolved=None):
    intent = catalog["intents"].get(plan["intent"])
    if intent is None:
        raise ValueError("UNSUPPORTED_INTENT")
    path = select_path(catalog, plan["intent"])
    graph_uri = catalog["graph"]
    if not re.fullmatch(r"https?://[^\s<>\"{}|^\\\\]+", graph_uri):
        raise ValueError("INVALID_GRAPH_URI")
    lines = ["?equipment a core:BOMItemRecord .",
             "?equipment ebom:hasEngineeringLocalId " + json.dumps(normalize_tag(plan["equipment_tag"])) + " ."]
    if resolved:
        for name, key in (("equipment", "equipment_uri"), ("assembly", "assembly_uri")):
            uri = resolved[key]
            if not re.fullmatch(r"https?://[^\s<>\"{}|^\\\\]+", uri):
                raise ValueError("INVALID_RESOLVED_IRI")
            lines.append(f"VALUES ?{name} {{ <{uri}> }}")
    for edge in path:
        lines.append(f"?{edge['to']} a {catalog['nodes'][edge['to']]['rdf_type']} .")
        if edge["direction"] == "forward":
            lines.append(f"?{edge['from']} {edge['predicate']} ?{edge['to']} .")
        else:
            lines.append(f"?{edge['to']} {edge['predicate']} ?{edge['from']} .")
    for f in intent["required_filters"]:
        lines.append(f"?{f['node']} {f['predicate']} {json.dumps(f['value'])} .")
    for i, e in enumerate(intent["required_evidence"]):
        lines.append(f"?{e['node']} {e['predicate']} ?evidence{i} .")
    if set(plan["outputs"]) != set(intent["outputs"]):
        raise ValueError("UNSUPPORTED_OUTPUTS")
    for name in plan["outputs"]:
        field = intent["outputs"][name]
        lines.append(f"?{field['node']} {field['predicate']} ?{name} .")
    prefixes = "\n".join(f"PREFIX {k}: <{v}>" for k,v in sorted(catalog["prefixes"].items()))
    query = (prefixes + "\nSELECT DISTINCT " + " ".join("?" + n for n in plan["outputs"]) +
             " WHERE {\n  GRAPH <" + graph_uri + "> {\n    " +
             "\n    ".join(lines) + "\n  }\n}\nORDER BY ?engineeringId")
    parseQuery(query)
    return query

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--question", required=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    try:
        plan = parse_question(args.question)
        catalog = load_catalog()
        resolved = resolve_remote(plan["equipment_tag"], args.endpoint, catalog["graph"]) if args.execute else None
        query = compile_query(plan, catalog, resolved)
        result = {"status": "compiled", "plan": plan, "path": [e["id"] for e in select_path(catalog, plan["intent"])],
                  "resolution": resolved, "sparql": query}
        if args.execute:
            bindings = run_query(query, args.endpoint)["results"]["bindings"]
            result.update(status="executed", binding_count=len(bindings), results=bindings)
            if not bindings:
                result["note"] = "No records match the requested source-domain/group filters; no physical relationships inferred."
    except ValueError as exc:
        result = {"status": "unsupported", "reason": str(exc)}
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if result["status"] == "unsupported":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
