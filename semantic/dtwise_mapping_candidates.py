"""Build an unapproved cross-domain mapping candidate from ontology2 SHACL evidence.

Run:
  python -m semantic.dtwise_mapping_candidates

This tool discovers matching asset-identifier properties in the schema index.
It never approves a mapping, modifies the approved registry, or constructs a query plan.
GraphDB instance evidence must be added/reviewed separately.
"""
import argparse
import json
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parent / "ontology2" / "dtwise"
PAIR = (
    ("dexpi", "https://example.org/dexpi/hasAssetIdentifier"),
    ("opcuaconnectivity", "https://example.org/opcuaconnectivity/hasAssetIdentifier"),
)


def build_candidates(index):
    paths = index.get("shape_paths", [])
    evidence = []
    for domain, predicate in PAIR:
        matching = [p for p in paths if p.get("domain") == domain
                    and p.get("path") == predicate and p.get("evidence")]
        if not matching:
            raise ValueError(f"No SHACL evidence for {domain}: {predicate}")
        evidence.append(sorted({eid for p in matching for eid in p["evidence"]}))
    return [{
        "id": "dexpi-opcua-asset-identifier",
        "left_domain": PAIR[0][0],
        "right_domain": PAIR[1][0],
        "left_property": PAIR[0][1],
        "right_property": PAIR[1][1],
        "evidence_ids": sorted(set(evidence[0] + evidence[1])),
        "verified": False,
        "evidence_note": (
            "SHACL evidence supports each property independently; GraphDB "
            "confirmed a lexical join for FI_101 / XMEAS1. Neither proves "
            "universal semantic equivalence. Independent approval required."
        ),
        "instance_evidence": {
            "dexpi_local_id": "FI_101",
            "shared_asset_identifier": "https://aas.example.com/FI101",
            "opcua_signal_name": "XMEAS1",
        },
    }]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DIRECTORY / "dtwise-schema-index.json")
    parser.add_argument("--output", type=Path, default=DIRECTORY / "cross-domain-mapping-candidates.json")
    args = parser.parse_args()
    index = json.loads(args.index.read_text(encoding="utf-8"))
    candidates = build_candidates(index)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(candidates, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(candidates)} unverified candidate(s) to {args.output}")


if __name__ == "__main__":
    main()
