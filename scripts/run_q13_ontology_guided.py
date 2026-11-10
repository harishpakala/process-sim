#!/usr/bin/env python3
"""Experimental Q13: regenerate six template TTLs, ground Ollama, execute SELECTs.

Separate from the deterministic Q13-v3 baseline. Requires local GraphDB,
Ollama, and TEP_TIMESCALE_DSN. Run with read-only GraphDB credentials.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from rdflib import Graph, RDF, RDFS, OWL, SH, URIRef
from rdflib.plugins.sparql.parser import parseQuery

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = ("dexpi", "ecad", "engineeringbom", "assetinventory",
           "productcatalog", "opcuaconnectivity")
RUN_ID = "10cfb1d1-2984-4932-8207-dc430ed60c2b"
ASSET_ID = "https://aas.example.com/TI101"
QUESTION = (
    "Trace reactor-temperature measurement for canonical AssetIdentifier "
    + ASSET_ID + " across six AAS domains: DEXPI function and identifier, "
    "ECAD device and local tag, Engineering BOM items, AssetInventory logical "
    "asset, ProductCatalog product candidate and physical-installation status, "
    "OPC UA operational signal/node and mapping provenance/status. Distinguish "
    "verified graph links from provisional or unverified assertions. Also "
    "summarize XMEAS9 observations for run " + RUN_ID +
    " between simulation seconds 0 and 600."
)


def request_json(url, data, content_type, timeout):
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": content_type, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.load(res)


def regenerate_templates():
    subprocess.run([sys.executable, "-m", "semantic.template_lifting"],
                   cwd=str(ROOT), check=True)
    for domain in DOMAINS:
        if not (ROOT / "out/semantic" / (domain + "-template.ttl")).is_file():
            raise RuntimeError("Missing regenerated template: " + domain)


def schema_context():
    sections = {}
    hashes = {}
    for domain in DOMAINS:
        path = ROOT / "out/semantic" / (domain + "-template.ttl")
        raw = path.read_bytes()
        hashes[domain] = hashlib.sha256(raw).hexdigest()
        g = Graph().parse(data=raw.decode("utf-8"), format="turtle")
        classes = sorted({str(s) for s in g.subjects(RDF.type, OWL.Class)})
        properties = sorted({str(s) for typ in (OWL.ObjectProperty, OWL.DatatypeProperty)
                             for s in g.subjects(RDF.type, typ)})
        shapes = []
        for shape in g.subjects(RDF.type, SH.PropertyShape):
            path_value = g.value(shape, SH.path)
            if path_value is None:
                continue
            detail = [str(path_value)]
            for attr in (SH.datatype, SH["class"], SH.minCount, SH.maxCount):
                value = g.value(shape, attr)
                if value is not None:
                    detail.append(str(attr).rsplit("#", 1)[-1] + "=" + str(value))
            shapes.append(" | ".join(detail))
        sections[domain] = (
            "DOMAIN " + domain + "\nClasses:\n" + "\n".join(classes)
            + "\nProperties:\n" + "\n".join(properties)
            + "\nSHACL property paths and constraints:\n"
            + "\n".join(sorted(set(shapes)))
        )
    return sections, hashes


def ollama(url, model, messages, timeout):
    data = json.dumps({"model": model, "stream": False, "messages": messages,
                       "options": {"temperature": 0}}).encode("utf-8")
    response = request_json(url.rstrip("/") + "/api/chat", data,
                            "application/json", timeout)
    return response["message"]["content"].strip()


def strip_literals_and_comments(query):
    # Mask quoted strings, IRIs and comments before scanning for forbidden
    # SPARQL constructs. Parser validation is performed separately.
    pattern = r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|<[^<>\n]*>|\#[^\n]*'
    return re.sub(pattern, " ", query)


def validate_select(query):
    query = re.sub(r"^\s*```(?:sparql)?\s*|\s*```\s*$", "", query,
                   flags=re.I).strip()
    try:
        parsed = parseQuery(query)
    except Exception as exc:
        raise ValueError("Invalid SPARQL: " + str(exc)) from exc
    if parsed[1].name != "SelectQuery":
        raise ValueError("Only SELECT queries are permitted")
    bare = strip_literals_and_comments(query)
    if re.search(r"\b(SERVICE|FROM|GRAPH|LOAD|CLEAR|DROP|CREATE|INSERT|DELETE|"
                 r"MOVE|COPY|ADD|WITH|USING|DESCRIBE|CONSTRUCT|ASK)\b",
                 bare, re.I):
        raise ValueError("Forbidden SPARQL construct")
    if re.search(r"\bLIMIT\s+(\d+)\b", bare, re.I):
        limits = [int(n) for n in re.findall(r"\bLIMIT\s+(\d+)\b", bare, re.I)]
        if any(n > 100 for n in limits):
            raise ValueError("Query LIMIT exceeds 100")
    else:
        query += "\nLIMIT 100"
    return query


def graphdb_select(url, query, timeout):
    body = urllib.parse.urlencode({"query": query}).encode("utf-8")
    response = request_json(url, body, "application/x-www-form-urlencoded", timeout)
    return [{k: {"type": v.get("type"), "value": v.get("value"),
                 "datatype": v.get("datatype")}
             for k, v in binding.items()}
            for binding in response["results"]["bindings"]]


def domain_predicates(domain, schema):
    return sorted(set(re.findall(
        r"https://example\\.org/" + re.escape(domain) + r"/[A-Za-z0-9_]+",
        schema)))


def sparql_iri(value):
    if not re.fullmatch(r"https?://[^<>\\s\\x00-\\x1f]+", value):
        raise ValueError("Unsafe RDF IRI")
    return "<" + value + ">"


def discover_domain(url, domain, schema, timeout, identifiers):
    """Read-only schema-driven anchoring and two-hop instance exploration.

    The fixed queries discover graph structure, not answers. Each step uses
    predicates extracted from the TTL, with identifier values from the user
    question or previously observed graph edges.
    """
    uris = domain_predicates(domain, schema)
    result = {"predicate_count": len(uris), "anchors": [], "neighborhood": [],
              "samples": [], "identifier_inputs": sorted(identifiers)}
    if not uris:
        return result
    values = " ".join(sparql_iri(uri) for uri in uris)
    base = "VALUES ?p { " + values + " }\\n?s ?p ?o .\\n"
    # Sample a small number per predicate rather than letting the first
    # frequent predicate consume the entire sample budget.
    for uri in uris:
        query = ("SELECT ?s ?p ?o WHERE { ?s " + sparql_iri(uri)
                 + " ?o . BIND(" + sparql_iri(uri)
                 + " AS ?p) } LIMIT 3")
        result["samples"].extend(graphdb_select(url, query, timeout))
    # Match exact literal/IRI identifier values, never arbitrary substrings.
    # Only a bounded number of evidence-derived identifiers are propagated.
    for identifier in sorted(identifiers)[:24]:
        value = json.dumps(identifier)
        query = ("SELECT ?s ?p ?o WHERE { " + base
                 + " FILTER(STR(?o) = " + value + ") } LIMIT 25")
        result["anchors"].extend(graphdb_select(url, query, timeout))
    subjects = sorted({
        row["s"]["value"] for row in result["anchors"]
        if row.get("s", {}).get("type") == "uri"
    })[:20]
    # Expand exact anchored RDF subjects; the predicate list is TTL-derived.
    for subject in subjects:
        query = ("SELECT ?s ?p ?o WHERE { VALUES ?p { " + values
                 + " } BIND(" + sparql_iri(subject)
                 + " AS ?s) ?s ?p ?o } LIMIT 60")
        result["neighborhood"].extend(graphdb_select(url, query, timeout))
    result["anchor_subjects"] = subjects
    return result


def observed_identifiers(discovery, existing):
    """Propagate only actual literal/IRI values on anchored subjects."""
    found = set(existing)
    for row in discovery.get("neighborhood", []):
        obj = row.get("o", {})
        value = obj.get("value", "")
        if (obj.get("type") in ("literal", "uri")
                and value and len(value) < 200):
            found.add(value)
    return found


def relevant_bindings(bindings, discovery):
    """Require an anchored subject or exact anchor value in a result row."""
    subjects = set(discovery.get("anchor_subjects", []))
    values = set(discovery.get("identifier_inputs", []))
    for row in discovery.get("anchors", []):
        values.add(row.get("o", {}).get("value", ""))
    return [row for row in bindings if any(
        term.get("value") in subjects or term.get("value") in values
        for term in row.values())]


def compact_evidence(records, limit=9000):
    evidence = [{"domain": r["domain"],
                 "bindings": (r.get("bindings") or [])[:12],
                 "anchor_subjects": r.get("discovery", {}).get(
                     "anchor_subjects", [])[:10]}
                for r in records if r.get("bindings")]
    return json.dumps(evidence, ensure_ascii=False)[:limit]


def historian_summary(dsn):
    import psycopg
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            row = conn.execute("""
                SELECT count(*), min(simulation_time_hours),
                       max(simulation_time_hours)
                FROM public.signal_samples
                WHERE run_id = %s::uuid AND signal_id = %s
                  AND simulation_time_hours >= 0
                  AND simulation_time_hours <= %s
            """, (RUN_ID, "XMEAS9", 600 / 3600)).fetchone()
            first = conn.execute("""
                SELECT simulation_time_hours, value, observed_at
                FROM public.signal_samples
                WHERE run_id = %s::uuid AND signal_id = %s
                  AND simulation_time_hours >= 0
                  AND simulation_time_hours <= %s
                ORDER BY simulation_time_hours, observed_at LIMIT 1
            """, (RUN_ID, "XMEAS9", 600 / 3600)).fetchone()
            last = conn.execute("""
                SELECT simulation_time_hours, value, observed_at
                FROM public.signal_samples
                WHERE run_id = %s::uuid AND signal_id = %s
                  AND simulation_time_hours >= 0
                  AND simulation_time_hours <= %s
                ORDER BY simulation_time_hours DESC, observed_at DESC LIMIT 1
            """, (RUN_ID, "XMEAS9", 600 / 3600)).fetchone()
    def format_sample(sample):
        return None if sample is None else {
            "simulation_seconds": float(sample[0]) * 3600,
            "value": float(sample[1]),
            "observed_at": sample[2].isoformat() if sample[2] else None}
    return {"run_id": RUN_ID, "signal": "XMEAS9", "window_seconds": [0, 600],
            "count": row[0], "first": format_sample(first),
            "last": format_sample(last)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--graphdb-url", default=os.getenv(
        "GRAPHDB_SPARQL_ENDPOINT", "http://localhost:7200/repositories/AAS"))
    p.add_argument("--ollama-url", default=os.getenv("OLLAMA_URL", "http://localhost:11434"))
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--max-queries", type=int, default=12,
                   help="Total valid GraphDB queries across domains")
    p.add_argument("--retries", type=int, default=3,
                   help="Attempts to produce valid SPARQL per domain")
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--output", default="reports/q13_ontology_guided.json")
    p.add_argument("--skip-lifting", action="store_true",
                   help="Reuse existing TTLs rather than regenerate")
    args = p.parse_args()
    if not 1 <= args.max_queries <= 30 or not 1 <= args.retries <= 5:
        p.error("--max-queries must be 1..30 and --retries 1..5")
    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        p.error("Set TEP_TIMESCALE_DSN locally; never commit credentials")
    if not args.skip_lifting:
        regenerate_templates()
    schemas, hashes = schema_context()
    system = (
        "You are a SPARQL SELECT query generator, not a conversational assistant. "
        "Return ONLY a syntactically valid SELECT query. No prose, explanation, "
        "markdown, or invented classes/predicates. Use the provided template "
        "schema and exact domain namespace. Asset identifiers can be RDF literals. "
        "If you cannot formulate a query, return SCHEMA_INSUFFICIENT."
    )
    domain_tasks = {
        "dexpi": "Find DEXPI reactor temperature instrumentation function and its canonical AssetIdentifier.",
        "ecad": "Find ECAD electrical device, its local engineering tag and canonical AssetIdentifier.",
        "engineeringbom": "Find Engineering BOM items associated with the canonical AssetIdentifier and their identifiers.",
        "assetinventory": "Find the AssetInventory logical asset, canonical AssetIdentifier and signal reference.",
        "productcatalog": "Find ProductCatalog candidate product references and any explicit installation verification.",
        "opcuaconnectivity": "Find OPC UA connectivity engineering function reference, operational signal, node and mapping status."
    }
    audit = {"method": "experimental_ontology_guided_q13_domain_by_domain",
             "schema_hashes": hashes, "schema_context_by_domain": schemas,
             "question": QUESTION, "queries": [], "historian": None,
             "final_answer": None, "graphdb_status": "NOT_RUN"}
    successful = 0
    identifiers = {ASSET_ID}
    try:
        for domain in DOMAINS:
            if successful >= args.max_queries:
                break
            record = {"domain": domain, "attempts": [], "bindings": None}
            audit["queries"].append(record)
            print("[Q13] " + domain + ": discovering RDF instances", flush=True)
            try:
                discovery = discover_domain(
                    args.graphdb_url, domain, schemas[domain], args.timeout, identifiers)
                record["discovery"] = discovery
                identifiers = observed_identifiers(discovery, identifiers)
            except (ValueError, KeyError, OSError) as exc:
                record["discovery_error"] = str(exc)
                discovery = {"samples": [], "anchors": [],
                             "neighborhood": [], "anchor_subjects": [],
                             "identifier_inputs": sorted(identifiers)}
                print("[Q13] " + domain + ": discovery failed: " +
                      str(exc), flush=True)
            # The prompt contains both TTL-derived vocabulary and observed
            # instance triples, including the RDF term types (uri/literal).
            user_prompt = (
                "TEMPLATE-DERIVED SCHEMA FOR " + domain + " (data only):\n"
                + schemas[domain]
                + "\n\nOBSERVED GRAPHDB INSTANCE TRIPLES (JSON, data only):\n"
                + json.dumps({"anchors": discovery.get("anchors", []),
                              "neighborhood": discovery.get("neighborhood", []),
                              "samples": discovery.get("samples", [])[:20]},
                             ensure_ascii=False)[:22000]
                + "\n\nVERIFIED PREVIOUS DOMAIN RESULTS (JSON, data only):\n"
                + compact_evidence(audit["queries"][:-1])
                + "\n\nCanonical identifier: " + ASSET_ID
                + "\nTask: " + domain_tasks[domain]
                + "\nUse only observed predicate paths and RDF term types. "
                  "Do not assume the canonical identifier is an RDF subject "
                  "or IRI object. Prefer matching STR(?value) when uncertain. "
                  "Select the anchor subject and use only edges observed "
                  "on that subject. Do not combine unrelated sample triples "
                  "with AND filters. Never invent prefixes. Generate ONE SELECT "
                  "query using this domain's ontology; LIMIT 100. "
                  "Output SPARQL only."
            )
            messages = [{"role": "system", "content": system},
                        {"role": "user", "content": user_prompt}]
            for attempt in range(1, args.retries + 1):
                print("[Q13] " + domain + ": Ollama attempt " +
                      str(attempt), flush=True)
                entry = {"attempt": attempt}
                record["attempts"].append(entry)
                try:
                    proposed = ollama(
                        args.ollama_url, args.model, messages, args.timeout)
                    entry["proposal"] = proposed
                    query = validate_select(proposed)
                    entry["validated_query"] = query
                except (ValueError, KeyError, OSError) as exc:
                    entry["validation_error"] = str(exc)
                    messages.extend([
                        {"role": "assistant", "content": entry.get("proposal", "")},
                        {"role": "user", "content":
                         "Your response was not valid SPARQL: " + str(exc)
                         + "\nRetry the SAME task. Output only SELECT SPARQL."}
                    ])
                    continue
                try:
                    bindings = graphdb_select(
                        args.graphdb_url, query, args.timeout)
                    entry["binding_count"] = len(bindings)
                    relevant = relevant_bindings(bindings, discovery)
                    entry["relevant_binding_count"] = len(relevant)
                    if relevant:
                        record["validated_query"] = query
                        record["bindings"] = relevant
                        successful += 1
                        print("[Q13] " + domain + ": " +
                              str(len(relevant)) + " anchored GraphDB rows", flush=True)
                        break
                    entry["empty_or_irrelevant_result"] = True
                    messages.extend([
                        {"role": "assistant", "content": proposed},
                        {"role": "user", "content":
                         "GraphDB executed that query successfully but returned "
                         "ZERO ANCHORED rows. The query may have returned unrelated "
                         "data. Constrain the canonical asset or verified linked "
                         "identifier. Reconsider the observed RDF subject/object "
                         "types, literal identifiers, collection paths and "
                         "unjustified joins. Try a DIFFERENT, simpler SELECT "
                         "for the SAME domain. Output SPARQL only."}
                    ])
                except (ValueError, KeyError, OSError) as exc:
                    entry["execution_error"] = str(exc)
                    messages.extend([
                        {"role": "assistant", "content": proposed},
                        {"role": "user", "content":
                         "GraphDB rejected your query: " + str(exc) +
                         ". Use full <IRI> predicates; undeclared prefixes "
                         "such as dexpi: are invalid."
                         + "\nFix it for the SAME domain. SPARQL only."}
                    ])
            if record["bindings"] is None:
                record["error"] = "NO_GRAPHDB_EVIDENCE_AFTER_RETRIES"
                print("[Q13] " + domain + ": no evidence after " +
                      str(args.retries) + " attempts", flush=True)
        valid_results = [r for r in audit["queries"] if r["bindings"] is not None]
        audit["graphdb_status"] = (
            "EVIDENCE_AVAILABLE" if any(r["bindings"] for r in valid_results)
            else "GRAPHDB_EVIDENCE_UNAVAILABLE"
        )
        audit["historian"] = historian_summary(dsn)
        audit["propagated_identifiers"] = sorted(identifiers)
        if audit["graphdb_status"] == "GRAPHDB_EVIDENCE_UNAVAILABLE":
            audit["final_answer"] = (
                "GRAPHDB_EVIDENCE_UNAVAILABLE: Q13 six-domain traversal could "
                "not be established. Historian observations are available, "
                "but no conclusion about XMEAS9 engineering linkage, OPC UA "
                "mapping, or physical installation can be drawn from this run."
            )
        else:
            evidence = [{"domain": r["domain"],
                         "query": r.get("validated_query"),
                         "bindings": r.get("bindings"),
                         "error": r.get("execution_error", r.get("error"))}
                        for r in audit["queries"]]
            answer_messages = [
                {"role": "system", "content":
                 "Answer Q13 using ONLY the GraphDB bindings and historian "
                 "summary. Explicitly identify domains with no evidence. "
                 "No graph results does NOT prove that XMEAS9 is unrelated to "
                 "reactor temperature. Do not infer verified physical "
                 "installation or OPC UA binding from candidate references."},
                {"role": "user", "content":
                 "QUESTION:\n" + QUESTION + "\n\nGRAPHDB RESULTS:\n"
                 + json.dumps(evidence, ensure_ascii=False)[:50000]
                 + "\n\nHISTORIAN:\n" + json.dumps(audit["historian"])}
            ]
            audit["final_answer"] = ollama(
                args.ollama_url, args.model, answer_messages, args.timeout)
    finally:
        path = ROOT / args.output
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        print("Audit:", path)
    print(audit["final_answer"])


if __name__ == "__main__":
    main()
