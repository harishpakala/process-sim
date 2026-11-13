"""Experiment 36C: evidence-gated nested SHACL path planning.

Discovers only directed edges of the form:
  source node shape --sh:path(property shape)--> target node shape
where the same property shape has an explicit sh:node relationship.
Each edge carries both SHACL evidence IDs. No inferred links, reverse
edges, or cross-domain joins are allowed.

 python experiments/vector_graph_rag/36_multihop_planner.py --inspect
 python experiments/vector_graph_rag/36_multihop_planner.py --self-test
 python experiments/vector_graph_rag/36_multihop_planner.py --plan path/to/plan.json
 python experiments/vector_graph_rag/36_multihop_planner.py --plan path/to/plan.json --execute

Plan:
 {"operation":"nested_path_select","predicates":["URI1","URI2"],
  "limit":10}
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
SH_NODE = "http://www.w3.org/ns/shacl#node"
IRI = re.compile(r"^https?://[^\s<>\"{}|^`\\]+$")

class PlanRejected(ValueError):
    pass

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def catalog(index):
    props = {c["uri"]: c for c in index.get("concepts", [])
             if c.get("kind") == "property" and c.get("uri")}
    node_links = {}
    for rel in index.get("relationships", []):
        if rel.get("predicate") == SH_NODE:
            node_links.setdefault((rel.get("domain"), rel.get("subject")), []).append(rel)
    edges = []
    for path in index.get("shape_paths", []):
        uri = path.get("path")
        if uri not in props:
            continue
        for rel in node_links.get((path.get("domain"), path.get("property_shape")), []):
            if not all([path.get("domain"), path.get("node_shape"),
                        path.get("property_shape"), rel.get("object")]):
                continue
            edges.append({
                "domain": path["domain"], "source_shape": path["node_shape"],
                "predicate": uri, "target_shape": rel["object"],
                "property_shape": path["property_shape"],
                "evidence": {"shape_path_relationships": path.get("evidence", []),
                             "target_node_relationship": rel.get("id")}
            })
    return props, edges

def paths_for(index, selected):
    props, edges = catalog(index)
    if any(not isinstance(uri, str) or not IRI.fullmatch(uri) or uri not in props
           for uri in selected):
        raise PlanRejected("Unknown or invalid ontology property URI")
    matches = []
    for first in edges:
        if first["predicate"] != selected[0]:
            continue
        sequences = [[first]]
        for uri in selected[1:]:
            sequences = [seq + [edge] for seq in sequences for edge in edges
                         if edge["predicate"] == uri
                         and edge["domain"] == seq[-1]["domain"]
                         and edge["source_shape"] == seq[-1]["target_shape"]]
        matches.extend(sequences)
    # Distinct shape paths, not multiple equivalent copies of the same evidence.
    unique = {}
    for seq in matches:
        signature = tuple((e["domain"], e["source_shape"], e["predicate"],
                           e["target_shape"]) for e in seq)
        unique[signature] = seq
    return list(unique.values())

def compile_plan(plan, index):
    if not isinstance(plan, dict) or set(plan) != {"operation", "predicates", "limit"}:
        raise PlanRejected("Expected only operation, predicates, limit")
    if plan["operation"] != "nested_path_select":
        raise PlanRejected("Only nested_path_select is supported")
    selected = plan["predicates"]
    if not isinstance(selected, list) or not 2 <= len(selected) <= 3:
        raise PlanRejected("Require two or three directed predicates")
    if len(set(selected)) != len(selected):
        raise PlanRejected("Repeated predicates are unsupported")
    limit = plan["limit"]
    if type(limit) is not int or not 1 <= limit <= 100:
        raise PlanRejected("Limit must be an integer from 1 to 100")
    matches = paths_for(index, selected)
    if len(matches) != 1:
        raise PlanRejected(f"Expected unique SHACL-evidenced directed path; found {len(matches)}")
    chain = matches[0]
    triples = [f"  ?node{i} <{uri}> ?node{i+1} ." for i, uri in enumerate(selected)]
    query = ("SELECT DISTINCT " +
             " ".join(f"?node{i}" for i in range(len(selected) + 1)) +
             " WHERE {\n" + "\n".join(triples) + f"\n}}\nLIMIT {limit}")
    return {"status": "compiled", "operation": "nested_path_select",
            "query": query, "path_evidence": chain,
            "caveat": "SHACL nested-node structure supports the path, but does not prove instance triples exist"}

def candidate_paths(index, max_hops=3):
    _, edges = catalog(index)
    out = []
    for first in edges:
        seqs = [[first]]
        for depth in range(2, max_hops + 1):
            seqs = [seq + [e] for seq in seqs for e in edges
                    if e["source_shape"] == seq[-1]["target_shape"]
                    and e["domain"] == seq[-1]["domain"]
                    and e["predicate"] not in [s["predicate"] for s in seq]]
            for seq in seqs:
                selected = [e["predicate"] for e in seq]
                if len(paths_for(index, selected)) == 1:
                    out.append({"domain": seq[0]["domain"], "predicates": selected})
    return sorted(out, key=lambda x: (len(x["predicates"]), x["domain"], x["predicates"]))

def self_test(index):
    paths = candidate_paths(index)
    if not paths:
        print("No uniquely supported multi-hop paths in current index; abstention is correct.")
    else:
        first = paths[0]
        plan = {"operation": "nested_path_select",
                "predicates": first["predicates"], "limit": 10}
        result = compile_plan(plan, index)
        assert result["query"].count(" .") == len(first["predicates"])
        print("Compiled evidence-supported path:", json.dumps(first))
        print(result["query"])
    for bad in [
        {"operation": "nested_path_select", "predicates": ["https://invalid.example/a", "https://invalid.example/b"], "limit": 10},
        {"operation": "nested_path_select", "predicates": ["https://invalid.example/a", "https://invalid.example/b"], "limit": 101},
        {"operation": "nested_path_select", "predicates": ["https://invalid.example/a", "https://invalid.example/b"], "limit": 10, "raw_sparql": "DELETE WHERE {}"},
        {"operation": "nested_path_select", "predicates": [], "limit": 10}
    ]:
        try:
            compile_plan(bad, index)
        except PlanRejected:
            pass
        else:
            raise AssertionError("Unsafe plan accepted")
    print("Self-test passed: fail-closed cases; compiled path if available")

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path, default=INDEX)
    ap.add_argument("--plan", type=Path)
    ap.add_argument("--output", type=Path, default=HERE / "data/ontology_multihop_36_results.json")
    ap.add_argument("--inspect", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--endpoint", default="http://localhost:7200/repositories/AAS")
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args()
    index = read(args.index)
    if args.inspect:
        props, edges = catalog(index)
        paths = candidate_paths(index)
        print(json.dumps({"indexed_properties": len(props),
                          "explicit_shacl_node_edges": len(edges),
                          "unique_nested_paths": len(paths),
                          "examples": paths[:10]}, indent=2))
        return
    if args.self_test:
        self_test(index)
        return
    if args.plan is None:
        ap.error("--plan required")
    if args.timeout < 1:
        ap.error("timeout must be positive")
    result = compile_plan(read(args.plan), index)
    result["index_sha256"] = hashlib.sha256(args.index.read_bytes()).hexdigest()
    result["execution"] = "not_requested"
    if args.execute:
        spec = spec_from_file_location("exp36c_32", HERE / "32_execute_simple_sparql.py")
        mod = module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        bindings = mod.execute(args.endpoint, result["query"], args.timeout)
        result.update({"execution": "ok", "returned_rows": len(bindings),
                       "nonempty": bool(bindings), "sample_bindings": bindings[:3]})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "query": result["query"],
                      "execution": result["execution"],
                      "returned_rows": result.get("returned_rows"),
                      "output": str(args.output)}, indent=2))

if __name__ == "__main__":
    main()
