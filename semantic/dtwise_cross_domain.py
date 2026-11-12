"""Evidence-gated cross-domain SPARQL for explicitly cataloged identifier mappings.

Run:
  python -m semantic.dtwise_cross_domain --query "Which EngineeringBOM items correspond to ECAD devices?" --allow-candidate
Default mode rejects candidate mappings. No LLM is allowed to invent joins.
"""
import argparse
import json
from pathlib import Path

from semantic.dtwise_sparql_compiler import _iri

DEFAULT_CATALOG = Path(__file__).parent / "ontology" / "dtwise" / "cross-domain-mappings.json"


def _validate_path(index, domain, path):
    if not path or not all(isinstance(x, str) and x.startswith("https://example.org/" + domain + "/") for x in path):
        raise ValueError("Mapping path crosses an unexpected namespace")
    if index is None:
        raise ValueError("Schema index required to validate join paths")
    known = {c["uri"] for c in index.get("concepts", []) if c.get("domain") == domain}
    known.update(p for entry in index.get("shape_paths", []) if isinstance(entry, dict)
                 for p in ([entry.get("path")] if isinstance(entry.get("path"), str) else []))
    # Verify each complete traversal using the existing SHACL resolver.
    from semantic.dtwise_concept_resolver import _traversals
    traversals = _traversals(index, path[-1], domain)
    if not any(t.get("complete_to_root") and t.get("property_chain") == path for t in traversals):
        raise ValueError("Catalog traversal is not grounded in SHACL: " + domain)


def compile_cross_domain(question, index, catalog, allow_candidate=False, limit=100):
    if not isinstance(limit, int) or not 1 <= limit <= 10000:
        raise ValueError("LIMIT must be between 1 and 10000")
    from semantic.dtwise_concept_resolver import _mentioned_domains
    mentioned = {d.lower() for d in _mentioned_domains(question)}
    if len(mentioned) == 3:\n        return _compile_three_domain(question, index, catalog, mentioned, allow_candidate, limit)\n    if len(mentioned) != 2:\n        raise ValueError("Cross-domain queries require two or three explicit domains")\n    matches = [m for m in catalog.get("mappings", []) if
               {m["source_domain"], m["target_domain"]} == mentioned]
    if len(matches) != 1:
        raise ValueError("Expected exactly one explicit catalog mapping for the two requested domains")
    mapping = matches[0]
    status = mapping.get("status")
    if status != "verified" and not (allow_candidate and status == "candidate_pending_semantic_approval"):
        raise ValueError("Join mapping is not semantically approved; use --allow-candidate for exploratory execution")
    if mapping.get("comparison") != "string_equality":
        raise ValueError("Unsupported join comparison")
    source, target = mapping["source_path"], mapping["target_path"]
    _validate_path(index, mapping["source_domain"], source)
    _validate_path(index, mapping["target_domain"], target)
    def triples(path, root, terminal, prefix):
        result = []
        for i, predicate in enumerate(path):
            subj = root if i == 0 else "?" + prefix + str(i)
            obj = terminal if i == len(path) - 1 else "?" + prefix + str(i + 1)
            result.append("  " + subj + " " + _iri(predicate) + " " + obj + " .")
        return result
    # The penultimate nodes represent records/devices, not identifier literals.
    left = triples(source, "?ebomRoot", "?ebomId", "eb")
    right = triples(target, "?ecadRoot", "?ecadId", "ec")
    source_entity = "?eb" + str(len(source) - 1)
    target_entity = "?ec" + str(len(target) - 1)
    body = "\n".join(left + right + ["  FILTER(STR(?ebomId) = STR(?ecadId))"])
    sparql = ("SELECT DISTINCT ?ebomId " + source_entity + " " + target_entity +
              " WHERE {\n" + body + "\n} LIMIT " + str(limit))
    return {"question": question, "mapping_id": mapping["id"], "mapping_status": status,
            "candidate_opt_in": bool(allow_candidate), "sparql": sparql,
            "execution_status": "not_executed", "cross_domain_join": "candidate" if status != "verified" else "verified"}


def _compile_three_domain(question, index, catalog, mentioned, allow_candidate, limit):
    """Compile only the explicitly cataloged EBOM/ECAD/DEXPI identifier join."""
    expected = {"engineeringbom", "ecad", "dexpi"}
    if mentioned != expected:
        raise ValueError("No cataloged three-domain plan for requested domains")
    mappings = [m for m in catalog.get("mappings", [])
                if {m.get("source_domain"), m.get("target_domain")} ==
                {"engineeringbom", "ecad"}]
    if len(mappings) != 1:
        raise ValueError("Three-domain plan requires exactly one EBOM/ECAD mapping")
    base = mappings[0]
    dexpi = [m for m in catalog.get("three_domain_mappings", [])
             if set(m.get("domains", [])) == expected]
    if len(dexpi) != 1:
        raise ValueError("No unique explicit three-domain mapping")
    plan = dexpi[0]
    for entry in (base, plan):
        status = entry.get("status")
        if status != "verified" and not (
                allow_candidate and status == "candidate_pending_semantic_approval"):
            raise ValueError("Join mapping is not semantically approved; use --allow-candidate for exploratory execution")
        if entry.get("comparison") != "string_equality":
            raise ValueError("Unsupported join comparison")
    source, target = base["source_path"], base["target_path"]
    _validate_path(index, "engineeringbom", source)
    _validate_path(index, "ecad", target)
    paths = plan.get("dexpi_paths", [])
    if not paths or len({tuple(p) for p in paths}) != len(paths):
        raise ValueError("DEXPI paths missing or duplicated")
    for p in paths:
        _validate_path(index, "dexpi", p)
        if p[-1] != "https://example.org/dexpi/hasAssetIdentifier":
            raise ValueError("DEXPI path must terminate at the cataloged asset identifier")
    def chain(path, prefix, entity, identifier):
        lines = []
        for i, predicate in enumerate(path):
            subject = "?" + prefix + "Root" if i == 0 else "?" + prefix + str(i)
            obj = identifier if i == len(path) - 1 else (
                entity if i == len(path) - 2 else "?" + prefix + str(i + 1))
            lines.append("    " + subject + " " + _iri(predicate) + " " + obj + " .")
        return lines
    left = chain(source, "eb", "?bomRecord", "?assetId")
    right = chain(target, "ec", "?device", "?ecadId")
    branches = []
    for i, p in enumerate(paths):
        branches.append("  {\n" + "\n".join(chain(p, "dx" + str(i), "?dexpiObject", "?dexpiId")) + "\n  }")
    body = "\n".join(left + right) + "\n  " + "\n  UNION\n  ".join(branches)
    body += "\n  FILTER(STR(?assetId) = STR(?ecadId))"
    body += "\n  FILTER(STR(?assetId) = STR(?dexpiId))"
    sparql = ("SELECT DISTINCT ?assetId ?bomRecord ?device ?dexpiObject WHERE {\n" +
              body + "\n} LIMIT " + str(limit))
    return {"question": question, "mapping_ids": [base["id"], plan["id"]],
            "mapping_status": plan["status"], "candidate_opt_in": bool(allow_candidate),
            "sparql": sparql, "execution_status": "not_executed",
            "cross_domain_join": "candidate" if any(
                m["status"] != "verified" for m in (base, plan)) else "verified"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--index", type=Path, default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--allow-candidate", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    result = compile_cross_domain(args.query, json.loads(args.index.read_text(encoding="utf-8")),
                                  json.loads(args.catalog.read_text(encoding="utf-8")),
                                  args.allow_candidate, args.limit)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
