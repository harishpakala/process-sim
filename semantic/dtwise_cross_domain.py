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
    from semantic.dtwise_n_domain_planner import compile_n_domain
    from semantic.dtwise_concept_resolver import _mentioned_domains
    mentioned = {d.lower() for d in _mentioned_domains(question)}
    return compile_n_domain(question, index, catalog, mentioned,
                            allow_candidate, limit, _validate_path)


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
