"""Classify historian signals from live, source-backed DEXPI/ECAD LocalIDs.

Dry run by default. No type or physical-sensor claim is made for ambiguous signals.
Use --apply only after reviewing the proposed changes and applying SQL migrations.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict

PREFIX_TYPES = {
    "T": "Temperature",
    "P": "Pressure",
    "L": "Level",
    "F": "Flow",
    "J": "Energy",
}
LOCAL_ID = re.compile(r"^([TPLFJ])[A-Z]?[-_][0-9]+$", re.IGNORECASE)


def classify_local_id(local_id):
    match = LOCAL_ID.fullmatch(local_id.strip())
    return PREFIX_TYPES[match.group(1).upper()] if match else None


def proposed_classifications(domain_mappings, available_signals):
    """Only classify when *all* linked LocalIDs agree and signal is in historian."""
    evidence = defaultdict(list)
    for domain, mappings in domain_mappings.items():
        for local_id, pairs in mappings.items():
            for asset, signal in pairs:
                if asset and signal in available_signals:
                    evidence[signal].append({"domain": domain, "local_id": local_id,
                                             "asset_identifier": asset,
                                             "candidate_type": classify_local_id(local_id)})
    proposals = []
    for signal in sorted(available_signals):
        entries = evidence.get(signal, [])
        types = {item["candidate_type"] for item in entries}
        kind = next(iter(types)) if len(types) == 1 and None not in types else None
        proposals.append({"signal_id": signal, "measurement_type": kind or "Unclassified",
                          "classification_source": "GraphDB DEXPI/ECAD LocalID prefix heuristic" if kind else "unclassified",
                          "verification_status": "PROVISIONAL" if kind else "NOT_VERIFIED",
                          "evidence": sorted(entries, key=lambda e: (e["domain"], e["local_id"], e["asset_identifier"])),
                          "reason": "consistent source-backed LocalID prefix" if kind else
                          ("conflicting or unsupported LocalIDs" if entries else "no live engineering mapping")})
    return proposals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write only consistent provisional classifications")
    args = parser.parse_args()
    dsn = os.environ.get("TEP_TIMESCALE_DSN")
    endpoint = os.environ.get("GRAPHDB_SPARQL_ENDPOINT")
    if not dsn or not endpoint:
        parser.error("TEP_TIMESCALE_DSN and GRAPHDB_SPARQL_ENDPOINT are required")
    import psycopg
    from process_sim.api.vtkg_query import discover_semantic_mappings
    mappings = {domain: discover_semantic_mappings(endpoint, domain) for domain in ("DEXPI", "ECAD")}
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT signal_id FROM public.signal_samples WHERE signal_id IS NOT NULL")
            signals = {row[0] for row in cur.fetchall()}
        proposals = proposed_classifications(mappings, signals)
        print(json.dumps({"mode": "apply" if args.apply else "dry_run", "proposals": proposals}, indent=2))
        if not args.apply:
            return
        with conn.cursor() as cur:
            # Store every source-backed association, including ambiguous and
            # unsupported LocalIDs; the evidence table is separate from samples.
            for item in proposals:
                for evidence in item["evidence"]:
                    cur.execute("""INSERT INTO public.signal_engineering_evidence
                        (signal_id, engineering_domain, local_id, asset_identifier,
                         mapping_source, inferred_measurement_type, observed_at)
                        VALUES (%s, %s, %s, %s, %s, %s, now())
                        ON CONFLICT (signal_id, engineering_domain, local_id, asset_identifier)
                        DO UPDATE SET mapping_source = EXCLUDED.mapping_source,
                                      inferred_measurement_type = EXCLUDED.inferred_measurement_type,
                                      observed_at = now()""",
                        (item["signal_id"], evidence["domain"], evidence["local_id"],
                         evidence["asset_identifier"], "GraphDB OPCUAConnectivity asset identifier join",
                         evidence["candidate_type"]))
            for item in proposals:
                if item["verification_status"] != "PROVISIONAL":
                    continue
                cur.execute("""INSERT INTO public.signal_metadata
                    (signal_id, measurement_type, classification_source, verification_status, updated_at)
                    VALUES (%s, %s, %s, 'PROVISIONAL', now())
                    ON CONFLICT (signal_id) DO UPDATE SET
                        measurement_type = EXCLUDED.measurement_type,
                        classification_source = EXCLUDED.classification_source,
                        verification_status = EXCLUDED.verification_status,
                        updated_at = now()
                    WHERE public.signal_metadata.verification_status = 'NOT_VERIFIED'
                      AND public.signal_metadata.measurement_type = 'Unclassified'""",
                    (item["signal_id"], item["measurement_type"], item["classification_source"]))
        conn.commit()


if __name__ == "__main__":
    main()
