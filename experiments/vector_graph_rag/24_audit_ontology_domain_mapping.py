"""Audit deterministic URI-to-domain resolution from the unified ontology index.

This is a mapping audit, NOT a domain relevance selector. Never uses gold labels
to resolve a retrieved concept. Unmapped or ambiguous URIs fail closed.
"""
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
MODES = ("lexical", "vector", "hybrid")


def ontology_map(index):
    owners = defaultdict(set)
    kinds = defaultdict(set)
    for c in index["concepts"]:
        if c.get("kind") not in ("class", "property"):
            continue
        uri, domain = c.get("uri"), c.get("domain")
        if not uri or not domain:
            raise ValueError("Ontology class/property missing uri or domain")
        owners[uri].add(domain)
        kinds[uri].add(c["kind"])
    return owners, kinds


def audit(index, retrieval, annotations=None, top_k=10):
    owners, kinds = ontology_map(index)
    ambiguous = {uri: sorted(ds) for uri, ds in owners.items() if len(ds) != 1}
    index_domains = sorted({d for ds in owners.values() for d in ds})
    by_id = {r["id"]: r for r in retrieval["results"]}
    if len(by_id) != len(retrieval["results"]):
        raise ValueError("Duplicate retrieval IDs")
    results = {}
    for mode in MODES:
        rows = []
        for qid, r in by_id.items():
            hits = r[mode]["hits"]
            resolved = []
            errors = []
            for rank, h in enumerate(hits, 1):
                uri = h.get("uri")
                ds = owners.get(uri, set())
                status = "resolved" if len(ds) == 1 else ("ambiguous" if ds else "unmapped")
                domain = next(iter(ds)) if len(ds) == 1 else None
                if status != "resolved":
                    errors.append({"rank": rank, "uri": uri, "status": status,
                                   "candidate_domains": sorted(ds)})
                elif h.get("domain") != domain:
                    errors.append({"rank": rank, "uri": uri, "status": "domain_mismatch",
                                   "stored_domain": h.get("domain"), "ontology_domain": domain})
                resolved.append({"rank": rank, "uri": uri, "domain": domain, "status": status})
            top = resolved[:top_k]
            top_domains = sorted({h["domain"] for h in top if h["status"] == "resolved"})
            rows.append({"id": qid, "hit_count": len(hits),
                         "resolved_count": sum(h["status"] == "resolved" for h in resolved),
                         "top_k_domains_union_diagnostic": top_domains,
                         "top_k_resolved": top, "errors": errors})
        total = sum(r["hit_count"] for r in rows)
        resolved_count = sum(r["resolved_count"] for r in rows)
        results[mode] = {
            "summary": {"questions": len(rows), "hits": total,
                        "resolved_hits": resolved_count,
                        "resolution_rate": resolved_count / total if total else None,
                        "unmapped_or_ambiguous_hits": total - resolved_count,
                        "domain_mismatches": sum(e["status"] == "domain_mismatch"
                                                 for r in rows for e in r["errors"])},
            "cases": rows,
        }
    reviewed = None
    if annotations is not None:
        reviewed_rows = []
        for case in annotations["cases"]:
            required = case["required"]
            errors = []
            for c in required:
                ds = owners.get(c["uri"], set())
                if len(ds) != 1 or c["domain"] not in ds:
                    errors.append({"uri": c["uri"], "annotated_domain": c["domain"],
                                   "ontology_domains": sorted(ds)})
            reviewed_rows.append({"id": case["id"], "required_concepts": len(required),
                                  "ontology_domain_errors": errors})
        reviewed = {"cases": reviewed_rows, "errors": sum(len(r["ontology_domain_errors"])
                                                           for r in reviewed_rows)}
    return {"experiment": "deterministic_ontology_concept_domain_audit",
            "ontology_concept_count": len(owners),
            "ontology_domains": index_domains,
            "ambiguous_ontology_uris": ambiguous,
            "top_k": top_k, "results": results, "reviewed_annotation_audit": reviewed,
            "limitations": [
                "The ontology index is a derived artifact; this audits its metadata, not raw TTL provenance.",
                "The top-k domain union is diagnostic only, not a predicted relevant domain set.",
                "Mapping an irrelevant retrieved concept correctly does not make its domain relevant.",
                "No gold expected domains are used in mapping; no instance joins are validated.",
            ]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path,
                    default=Path("semantic/ontology/dtwise/dtwise-schema-index.json"))
    ap.add_argument("--retrieval", type=Path, default=ROOT / "data/retrieval_results_15.json")
    ap.add_argument("--annotations", type=Path, default=ROOT / "data/reviewed_concepts_6.json")
    ap.add_argument("--output", type=Path, default=ROOT / "data/ontology_domain_mapping_audit.json")
    ap.add_argument("--top-k", type=int, default=10)
    args = ap.parse_args()
    if args.top_k < 1:
        ap.error("--top-k must be positive")
    load = lambda p: json.loads(p.read_text(encoding="utf-8-sig"))
    index, retrieval = load(args.index), load(args.retrieval)
    annotations = load(args.annotations) if args.annotations.exists() else None
    result = audit(index, retrieval, annotations, args.top_k)
    result["input_sha256"] = {name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for name, p in (("index", args.index), ("retrieval", args.retrieval))
                              if p.exists()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("Ontology concepts:", result["ontology_concept_count"],
          "ambiguous URIs:", len(result["ambiguous_ontology_uris"]))
    for mode, block in result["results"].items():
        s = block["summary"]
        print(f"{mode}: {s['resolved_hits']}/{s['hits']} hits resolved; "
              f"{s['unmapped_or_ambiguous_hits']} unresolved; "
              f"{s['domain_mismatches']} stored-domain mismatches")
    if result["reviewed_annotation_audit"] is not None:
        print("Reviewed required-concept domain errors:",
              result["reviewed_annotation_audit"]["errors"])
    print("Wrote:", args.output)


if __name__ == "__main__":
    main()
