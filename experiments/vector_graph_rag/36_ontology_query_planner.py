"""Experiment 36: evidence-grounded SPARQL plan compiler (first increment).

The DTWiSE schema index has SHACL shape_paths but no ontology_edges.
This module supports single predicates and two-property star patterns ONLY
when both paths are documented on the same SHACL node shape. Shared shape
membership is evidence for a common structural context, not proof of an
instance-level join or a cross-domain connection. No LLM is required yet.

Usage:
 python experiments/vector_graph_rag/36_ontology_query_planner.py --self-test
 python experiments/vector_graph_rag/36_ontology_query_planner.py --inspect
 python experiments/vector_graph_rag/36_ontology_query_planner.py --plan path/to/plan.json
 python experiments/vector_graph_rag/36_ontology_query_planner.py --plan path/to/plan.json --execute

Plan example:
 {"operation":"star_select","predicates":["https://example.org/assetinventory/hasAsset",
 "https://example.org/assetinventory/hasAssetIdentifier"],"limit":100}
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INDEX = ROOT / "semantic/ontology/dtwise/dtwise-schema-index.json"
IRI = re.compile(r"^https?://[^\s<>\"{}|^\x60\\]+$")

class PlanRejected(ValueError):
    pass

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def evidence_catalog(index):
    properties = {c["uri"]: c for c in index["concepts"]
                  if c.get("kind") == "property" and c.get("uri")}
    paths = {}
    for row in index.get("shape_paths", []):
        uri = row.get("path")
        if uri not in properties:
            continue
        key = (row.get("domain"), row.get("node_shape"))
        if not key[0] or not key[1]:
            continue
        paths.setdefault(key, {}).setdefault(uri, []).append({
            "property_shape": row.get("property_shape"),
            "relationship_evidence_ids": row.get("evidence", [])
        })
    return properties, paths

def validate_plan(plan, index):
    if not isinstance(plan, dict) or set(plan) != {"operation", "predicates", "limit"}:
        raise PlanRejected("Plan must contain only operation, predicates and limit")
    op, selected, limit = plan["operation"], plan["predicates"], plan["limit"]
    if op not in ("single_select", "star_select"):
        raise PlanRejected("Unsupported operation; cross-domain traversal is not implemented")
    count = 1 if op == "single_select" else 2
    if not isinstance(selected, list) or len(selected) != count or len(set(selected)) != count:
        raise PlanRejected(f"{op} requires {count} distinct predicate URI(s)")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise PlanRejected("limit must be an integer in 1..100")
    properties, paths = evidence_catalog(index)
    for uri in selected:
        if not isinstance(uri, str) or not IRI.fullmatch(uri) or uri not in properties:
            raise PlanRejected("Predicate is not a valid indexed ontology property")
    matching = []
    for (domain, node_shape), available in paths.items():
        if all(uri in available for uri in selected):
            matching.append({
                "domain": domain, "node_shape": node_shape,
                "predicate_evidence": {uri: available[uri] for uri in selected}
            })
    if not matching:
        raise PlanRejected("No common SHACL node-shape evidence for selected predicates")
    # Avoid silently selecting a shape among multiple possible structural contexts.
    if len(matching) != 1:
        raise PlanRejected(f"Ambiguous structural context: {len(matching)} matching node shapes")
    return matching[0]

def compile_plan(plan, index):
    evidence = validate_plan(plan, index)
    selected = plan["predicates"]
    lines = [f"  ?subject <{uri}> ?value{i} ." for i, uri in enumerate(selected, 1)]
    query = ("SELECT DISTINCT ?subject " +
             " ".join(f"?value{i}" for i in range(1, len(selected) + 1)) +
             " WHERE {\n" + "\n".join(lines) +
             f"\n}}\nLIMIT {plan['limit']}")
    return {"status": "compiled", "operation": plan["operation"],
            "query": query, "evidence": evidence,
            "semantics": "same-subject star; no asserted cross-domain path",
            "caveat": "SHACL shape-path co-membership does not prove matching instance triples"}

def self_test():
    index = read(INDEX)
    _, paths = evidence_catalog(index)
    groups = [(k, sorted(p)) for k, p in paths.items() if len(p) >= 2]
    if not groups:
        raise AssertionError("Index has no multi-path node shape")
    valid = None
    for (_, _), uris in groups:
        candidate = {"operation": "star_select", "predicates": uris[:2], "limit": 10}
        try:
            valid = compile_plan(candidate, index)
            break
        except PlanRejected:
            continue
    if valid is None:
        raise AssertionError("No uniquely evidenced two-predicate star found")
    assert valid["query"].count(" ?value") >= 2
    checks = [
        {"operation": "star_select", "predicates": ["https://invalid.example/x", "https://invalid.example/y"], "limit": 10},
        {"operation": "cross_domain_join", "predicates": uris[:2], "limit": 10},
        {"operation": "star_select", "predicates": uris[:2], "limit": 1000},
        {"operation": "star_select", "predicates": uris[:2], "limit": 10, "raw_sparql": "DELETE WHERE {}"},
    ]
    for bad in checks:
        try:
            compile_plan(bad, index)
        except PlanRejected:
            continue
        raise AssertionError("Unsafe plan accepted: " + repr(bad))
    print("Self-test passed: evidenced star compilation and four fail-closed cases")
    print(valid["query"])

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path, default=INDEX)
    ap.add_argument("--plan", type=Path)
    ap.add_argument("--output", type=Path, default=HERE / "data/ontology_planner_36_result.json")
    ap.add_argument("--endpoint", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--inspect", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    index = read(args.index)
    properties, paths = evidence_catalog(index)
    if args.inspect:
        print(json.dumps({"properties": len(properties),
                          "node_shape_contexts": len(paths),
                          "multi_property_contexts": sum(len(p) >= 2 for p in paths.values()),
                          "ontology_edges": len(index.get("ontology_edges", [])),
                          "supported_operations": ["single_select", "star_select"]}, indent=2))
        return
    if args.plan is None:
        ap.error("--plan required unless --inspect or --self-test")
    if args.timeout < 1:
        ap.error("timeout must be positive")
    result = compile_plan(read(args.plan), index)
    result["index_sha256"] = hashlib.sha256(args.index.read_bytes()).hexdigest()
    result["execution"] = "not_requested"
    if args.execute:
        spec = spec_from_file_location("exp36_sparql", HERE / "32_execute_simple_sparql.py")
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        bindings = mod.execute(args.endpoint, result["query"], args.timeout)
        result.update({"execution": "ok", "returned_rows": len(bindings),
                       "nonempty": bool(bindings), "sample_bindings": bindings[:3]})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "execution": result["execution"],
                      "output": str(args.output)}, indent=2))

if __name__ == "__main__":
    main()
