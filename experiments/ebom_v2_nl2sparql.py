#!/usr/bin/env python3
"""DTWiSE deterministic EBOM V2 NL-to-SPARQL vertical slice.

Supported intent: DEXPI instrumentation functions functionally associated with
an explicitly identified equipment tag, returning engineering ID, description,
and asset identifier. Entity resolution happens in RDF, not in hardcoded aliases.
Fail closed for other domains, outputs, or relationship semantics.

Examples:
 python experiments/ebom_v2_nl2sparql.py --question "Which DEXPI instrumentation functions are functionally associated with reactor R-001? Return their engineering identifiers, descriptions, and asset identifiers."
 python experiments/ebom_v2_nl2sparql.py --question "..." --execute
"""
import argparse
import json
import re
from pathlib import Path

GRAPH_URI = "https://example.org/dtwise/graph/ebom-v2"
DEFAULT_ENDPOINT = "http://localhost:7200/repositories/AAS"
TAG_RE = re.compile(r"\b[A-Za-z]{1,6}[-_][0-9]{1,8}\b")
ALLOWED_WORDS = {"which", "what", "list", "show", "give", "me", "all", "the", "dexpi",
    "instrumentation", "instrument", "instruments", "functions", "function", "are",
    "is", "functionally", "associated", "association", "with", "to", "of", "for",
    "equipment", "tag", "reactor", "condenser", "compressor", "separator", "stripper",
    "return", "their", "engineering", "identifiers", "identifier", "ids", "id",
    "descriptions", "description", "and", "asset", "from", "ebom", "bom",
    "according", "as", "in", "v2", "please", "?"}
# Named engineering equipment classes above are lexical context, not tag-to-assembly mappings.

def parse_intent(question):
    q = question.lower()
    if not ("dexpi" in q and re.search(r"instrumentation|instruments?\b", q)
            and re.search(r"functionally associated|functional association", q)):
        raise ValueError("UNSUPPORTED_INTENT: requires DEXPI instrumentation functional association")
    tags = sorted({m.group(0).upper().replace("_", "-") for m in TAG_RE.finditer(question)})
    if len(tags) != 1:
        raise ValueError("AMBIGUOUS_ENTITY: exactly one explicit equipment tag required")
    # Fail closed on semantics that could imply a different relation.
    if re.search(r"\b(physically|installed|mounted|contained|parts|components|procurement|quantity)\b", q):
        raise ValueError("UNSUPPORTED_RELATION: functional association is not physical membership")
    if re.search(r"\b(ecad|opc|historical|temporal|timeseries|product catalog|asset inventory)\b", q):
        raise ValueError("UNSUPPORTED_DOMAIN: this compiler supports only EBOM-to-DEXPI source records")
    # Outputs are fixed for this vertical slice; reject requests for additional fields.
    scrubbed = TAG_RE.sub(" ", q)
    unknown = {w for w in re.findall(r"[a-z][a-z0-9]*", scrubbed) if w not in ALLOWED_WORDS}
    if unknown:
        raise ValueError("UNSUPPORTED_TERMS: " + ", ".join(sorted(unknown)))
    return {"intent": "dexpi_instrumentation_functional_association",
            "equipment_tag": tags[0],
            "outputs": ["engineeringId", "description", "assetIdentifier"]}

def sparql_string(value):
    # JSON escaping is compatible with SPARQL double-quoted string literals.
    return json.dumps(value, ensure_ascii=False)

def compile_sparql(intent, graph_uri=GRAPH_URI):
    if intent.get("intent") != "dexpi_instrumentation_functional_association":
        raise ValueError("Unsupported intent")
    if not re.fullmatch(r"[A-Z]{1,6}-[0-9]{1,8}", intent["equipment_tag"]):
        raise ValueError("Invalid equipment tag")
    if not re.fullmatch(r"https?://[^\s<>\"{}|^\\\\]+", graph_uri):
        raise ValueError("Invalid graph IRI")
    tag = sparql_string(intent["equipment_tag"])
    return f"""PREFIX core: <https://example.org/dtwise/core/>
PREFIX ebom: <https://example.org/engineeringbom/>
SELECT DISTINCT ?engineeringId ?description ?assetIdentifier
WHERE {{
  GRAPH <{graph_uri}> {{
    ?equipment a core:BOMItemRecord ;
      ebom:hasEngineeringLocalId {tag} ;
      core:hasRecordedParent ?assembly .
    ?assembly a core:AssemblyRecord .
    ?association a core:FunctionalAssociation ;
      core:functionalAssociationTarget ?assembly ;
      core:functionalAssociationSource ?instrument ;
      core:associationBasis ?associationBasis ;
      core:sourceRecordId ?sourceRecordId .
    ?instrument a core:BOMItemRecord ;
      ebom:hasSourceDomain "DEXPI" ;
      ebom:hasSourceGroup "InstrumentationFunctions" ;
      ebom:hasEngineeringLocalId ?engineeringId ;
      ebom:hasItemDescription ?description ;
      ebom:hasAssetIdentifier ?assetIdentifier .
  }}
}}
ORDER BY ?engineeringId"""

def run_query(query, endpoint=DEFAULT_ENDPOINT):
    import requests
    response = requests.post(endpoint, data={"query": query},
                             headers={"Accept": "application/sparql-results+json"}, timeout=45)
    response.raise_for_status()
    return response.json()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--question", required=True)
    ap.add_argument("--graph", default=GRAPH_URI)
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        plan = parse_intent(args.question)
        query = compile_sparql(plan, args.graph)
        result = {"status": "compiled", "plan": plan, "sparql": query}
        if args.execute:
            answer = run_query(query, args.endpoint)
            result["status"] = "executed"
            result["binding_count"] = len(answer.get("results", {}).get("bindings", []))
            result["results"] = answer.get("results", {}).get("bindings", [])
    except (ValueError, RuntimeError) as e:
        result = {"status": "unsupported", "reason": str(e)}
    serialized = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    if result["status"] == "unsupported":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
