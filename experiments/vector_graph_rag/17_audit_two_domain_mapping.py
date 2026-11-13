"""Prepare evidence for human review of the EngineeringBOM–ECAD candidate mapping.

No GraphDB connection, mapping approval, or SPARQL execution. Generates
read-only SPARQL audits to run on the actual instance graph.
Run: python -m experiments.vector_graph_rag.17_audit_two_domain_mapping
"""
import argparse
import json
from pathlib import Path

from semantic.dtwise_cross_domain import _validate_path
from semantic.dtwise_n_domain_planner import compile_n_domain

INDEX = Path("semantic/ontology/dtwise/dtwise-schema-index.json")
CATALOG = Path("semantic/ontology/dtwise/cross-domain-mappings.json")
OUTPUT = Path("experiments/vector_graph_rag/data/two_domain_mapping_audit.json")
MAPPING_ID = "engineeringbom_ecad_asset_identifier"


def triples(path, prefix):
    lines = []
    for i, predicate in enumerate(path):
        subject = "?" + prefix + ("root" if i == 0 else "n" + str(i))
        obj = "?" + prefix + ("id" if i == len(path)-1 else "n" + str(i+1))
        lines.append("  " + subject + " <" + predicate + "> " + obj + " .")
    return "\n".join(lines)


def build(index, catalog):
    matches = [m for m in catalog.get("mappings", []) if m.get("id") == MAPPING_ID]
    if len(matches) != 1:
        raise ValueError("Expected exactly one EngineeringBOM–ECAD mapping")
    mapping = matches[0]
    if {mapping["source_domain"], mapping["target_domain"]} != {"engineeringbom", "ecad"}:
        raise ValueError("Unexpected mapping domains")
    for domain, path in ((mapping["source_domain"], mapping["source_path"]),
                         (mapping["target_domain"], mapping["target_path"])):
        _validate_path(index, domain, path)
    bom = triples(mapping["source_path"], "bom")
    ecad = triples(mapping["target_path"], "ecad")
    join = "  FILTER(STR(?bomid) = STR(?ecadid))"
    paired = bom + "\n" + ecad + "\n" + join
    queries = {
        "sample_matched_pairs": (
            "SELECT DISTINCT ?bomn2 ?ecadn2 ?bomid ?ecadid WHERE {\n"
            + paired + "\n} LIMIT 100"
        ),
        "matched_pair_cardinality": (
            "SELECT (COUNT(*) AS ?matchedRows) "
            "(COUNT(DISTINCT ?bomn2) AS ?distinctBOMRecords) "
            "(COUNT(DISTINCT ?ecadn2) AS ?distinctECADDevices) "
            "(COUNT(DISTINCT STR(?bomid)) AS ?distinctIdentifiers) WHERE {\n"
            + paired + "\n}"
        ),
        "duplicate_bom_identifiers": (
            "SELECT ?bomid (COUNT(DISTINCT ?bomn2) AS ?recordCount) WHERE {\n"
            + bom + "\n} GROUP BY ?bomid HAVING (COUNT(DISTINCT ?bomn2) > 1) LIMIT 100"
        ),
        "duplicate_ecad_identifiers": (
            "SELECT ?ecadid (COUNT(DISTINCT ?ecadn2) AS ?deviceCount) WHERE {\n"
            + ecad + "\n} GROUP BY ?ecadid HAVING (COUNT(DISTINCT ?ecadn2) > 1) LIMIT 100"
        ),
        "unmatched_bom_identifiers": (
            "SELECT DISTINCT ?bomn2 ?bomid WHERE {\n" + bom
            + "\n  FILTER NOT EXISTS {\n" + ecad
            + "\n    FILTER(STR(?bomid) = STR(?ecadid))\n  }\n} LIMIT 100"
        ),
    }
    exploratory = compile_n_domain(
        "Which EngineeringBOM records correspond to ECAD devices?",
        index, catalog, {"engineeringbom", "ecad"}, True, 100, _validate_path
    )
    return {
        "mapping_id": MAPPING_ID,
        "catalog_status": mapping.get("status"),
        "catalog_evidence_prior_observations_not_revalidated": mapping.get("evidence", {}),
        "identifier_namespace_claim": mapping.get("identifier_namespace"),
        "schema_paths_validated": True,
        "exploratory_plan_status": exploratory.get("cross_domain_join"),
        "queries_not_executed": queries,
        "review_questions": [
            "Do both identifier properties refer to the same real-world asset identity?",
            "Are the identifier issuing authority, namespace, normalization, and scope identical?",
            "Are repeated BOM records for one identifier expected and distinguishable?",
            "Are ECAD devices uniquely identified within the intended scope?",
            "Are unmatched or conflicting records understood and documented?",
            "Has an authorized domain expert reviewed sample matched pairs and approved the mapping?"
        ],
        "semantic_mapping_approved": False,
        "execution_performed": False,
        "limitations": [
            "The queries assume the catalog paths point to the intended instance graph.",
            "String equality does not establish semantic identity.",
            "Query outputs require inspection before any governance approval.",
            "Do not change catalog status based only on counts."
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=INDEX)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = build(json.loads(args.index.read_text(encoding="utf-8")),
                   json.loads(args.catalog.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"mapping_id": result["mapping_id"], "status": result["catalog_status"],
                      "schema_paths_validated": result["schema_paths_validated"],
                      "audit_queries": list(result["queries_not_executed"]),
                      "semantic_mapping_approved": False, "execution_performed": False}, indent=2))
    print("Wrote:", args.output)


if __name__ == "__main__":
    main()
