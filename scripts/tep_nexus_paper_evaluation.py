#!/usr/bin/env python3
"""Read-only, evidence-first TEP NEXUS paper evaluation.

Run from repository root. No fault is injected by this program.
Unknown cross-domain joins are never inferred from similar-looking tags.
"""

# Created: 2026-11-02
# Author: Harish
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ASSETS = {
    "pressure": ("TEP_XMEAS7", "PI-1101", "XMEAS7"),
    "flow": ("TEP_XMEAS6", "FI-1101", "XMEAS6"),
    "temperature": ("TEP_XMEAS9", "TI-1101", "XMEAS9"),
    "level": ("TEP_XMEAS8", "LI-1101", "XMEAS8"),
}
QUESTIONS = [
    ("Which instruments are associated with the reactor?", ["DEXPI"]),
    ("What are their electrical references?", ["DEXPI", "ECAD"]),
    ("What are their asset IDs and signal references?", ["DEXPI", "AssetInventory"]),
    ("Which products and manufacturers are associated with these assets?", ["AssetInventory", "ProductCatalog"]),
    ("What are their ECLASS and QUDT attributes?", ["ProductCatalog"]),
    ("Which asset identifiers link the engineering representations?", ["DEXPI", "ECAD", "AssetInventory"]),
    ("What engineering information is available for PI-1101?", ["DEXPI", "ECAD", "AssetInventory", "ProductCatalog"]),
    ("Which fault was activated, and when?", ["fault_events"]),
    ("For the selected reactor-related TEP signals XMEAS6, XMEAS7, XMEAS8, and XMEAS9, what were their recorded values and simulation timestamps immediately before and at the paper-fault-01 operator injection command at simulation time 30 seconds in the selected simulation run?", ["AssetInventory", "signal_samples", "fault_events"]),
    ("For the reactor feed-flow instrument FI-1101, provide its canonical AAS AssetIdentifier, DEXPI reference, ECAD reference, associated product candidate, ECLASS class, and operational signal. Also report the recorded XMEAS6 values and simulation timestamps immediately before and at the paper-fault-01 operator injection command at simulation time 30 seconds in the selected simulation run.", ["DEXPI", "ECAD", "AssetInventory", "ProductCatalog", "signal_samples", "fault_events"]),
]


def properties(collection):
    return {e["idShort"]: e.get("value") for e in collection
            if e.get("modelType") == "Property"}


def records(path):
    document = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if document.get("modelType") != "Submodel":
        raise ValueError(f"Expected AAS Submodel: {path}")
    # AAS instance collections contain nested SubmodelElementCollections.
    result = {}
    for group in document.get("submodelElements", []):
        for item in group.get("value", []):
            fields = properties(item.get("value", []))
            technical = next((e for e in item.get("value", [])
                              if e.get("idShort") == "TechnicalProperties"), None)
            if technical:
                fields["TechnicalProperties"] = properties(technical.get("value", []))
            result[item["idShort"]] = fields
    return result


def engineering_evidence(asset_path, product_path):
    assets = records(asset_path)
    products = records(product_path)
    by_uri = {v.get("ProductIdentifier"): (k, v) for k, v in products.items()}
    evidence = {}
    for kind, (asset_key, tag, signal) in ASSETS.items():
        if asset_key not in assets:
            raise ValueError(f"Missing asset: {asset_key}")
        asset = assets[asset_key]
        if asset.get("EquipmentTag") != tag or asset.get("OperationalReference") != signal:
            raise ValueError(f"Unexpected tag/signal for {asset_key}")
        product_ref = asset.get("ProductIdentifier")
        product = by_uri.get(product_ref)
        if not product:
            raise ValueError(f"Unresolved ProductIdentifier for {asset_key}: {product_ref}")
        product_key, product_fields = product
        tech = product_fields.get("TechnicalProperties", {})
        # Preserve catalog specifications alongside their QUDT semantics.
        qudt = {k: v for k, v in tech.items() if "QUDT" in k}
        specification_keys = (
            "MeasurementRange", "FactoryConfiguredRange", "FamilyMeasuringRange",
            "MaximumMeasuringDistance", "Accuracy", "PressureReference",
        )
        specifications = {k: tech[k] for k in specification_keys if k in tech}
        evidence[kind] = {
            "asset_id": asset.get("AssetIdentifier"),
            "asset_key": asset_key,
            "equipment_tag": tag,
            "asset_name": asset.get("AssetName"),
            "signal": signal,
            "plc_mapping_in_asset_inventory": asset.get("PLCMapping"),
            "product_uri": product_ref,
            "product_key": product_key,
            "manufacturer": product_fields.get("ManufacturerName"),
            "eclass_class": product_fields.get("ECLASSClass"),
            "eclass_preferred_name": product_fields.get("ECLASSPreferredName"),
            "eclass_irdi": product_fields.get("ECLASSIRDI"),
            "eclass_verification": product_fields.get("ECLASSVerificationStatus"),
            "qudt_product_specification": qudt,
            "catalog_technical_specifications": specifications,
            "product_selection_status": product_fields.get("SelectionStatus"),
            "installation_verification": product_fields.get("InstallationVerificationStatus"),
            "asset_simulation_status": asset.get("SimulationStatus"),
        }
    return evidence


def temporal_evidence(dsn, run_id, signals):
    """Only persisted fault commands and actual samples; never manufacture a fault."""
    import psycopg
    result = {"run_id": run_id, "fault_events": [], "measurements": {}}
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            events = conn.execute(
                """SELECT event_id, fault_id, action, simulation_time_hours,
                          event_source, observed_at
                   FROM public.fault_events
                   WHERE run_id = %s::uuid
                   ORDER BY simulation_time_hours, observed_at""",
                (run_id,),
            ).fetchall()
            for event_id, fault_id, action, hours, source, observed_at in events:
                result["fault_events"].append({
                    "event_id": str(event_id), "fault_id": fault_id,
                    "action": action, "simulation_seconds": float(hours) * 3600,
                    "event_source": source, "observed_at": observed_at.isoformat(),
                })
            # An activation is a recorded operator command, not verified physical causality.
            activation = next((e for e in result["fault_events"]
                               if e["action"].lower() in {"activate", "inject", "enable", "start"}), None)
            result["selected_activation"] = activation
            if activation:
                onset = activation["simulation_seconds"] / 3600
                for signal in signals:
                    before = conn.execute(
                        """SELECT simulation_time_hours, value, observed_at
                           FROM public.signal_samples
                           WHERE run_id = %s::uuid AND signal_id = %s
                             AND simulation_time_hours < %s
                           ORDER BY simulation_time_hours DESC, observed_at DESC LIMIT 1""",
                        (run_id, signal, onset),
                    ).fetchone()
                    after = conn.execute(
                        """SELECT simulation_time_hours, value, observed_at
                           FROM public.signal_samples
                           WHERE run_id = %s::uuid AND signal_id = %s
                             AND simulation_time_hours >= %s
                           ORDER BY simulation_time_hours ASC, observed_at ASC LIMIT 1""",
                        (run_id, signal, onset),
                    ).fetchone()
                    def sample(row):
                        return None if row is None else {
                            "simulation_seconds": float(row[0]) * 3600,
                            "value": float(row[1]), "observed_at": row[2].isoformat(),
                        }
                    result["measurements"][signal] = {"before": sample(before), "after": sample(after)}
    return result


def verified_graphdb_mappings(endpoint):
    """Require exact four-domain joins, including the expected operational signals."""
    import requests
    query = """
    PREFIX dx: <https://example.org/dexpi/>
    PREFIX ec: <https://example.org/ecad/>
    PREFIX ai: <https://example.org/assetinventory/>
    PREFIX pc: <https://example.org/productcatalog/>
    SELECT DISTINCT ?assetId ?dexpiLocal ?ecadLocal ?signal ?productId ?eclassCode
    WHERE {
      ?d dx:hasAssetIdentifier ?assetId ; dx:hasLocalId ?dexpiLocal .
      ?e ec:hasAssetIdentifier ?ecadId ; ec:hasLocalId ?ecadLocal .
      ?a ai:hasAssetIdentifier ?invId ;
         ai:hasOperationalReference ?signal ;
         ai:hasProductIdentifier ?productId .
      ?p pc:hasProductIdentifier ?catalogId .
      OPTIONAL { ?p pc:hasECLASSClass ?eclassCode }
      FILTER(STR(?assetId) = STR(?ecadId) &&
             STR(?assetId) = STR(?invId) &&
             STR(?productId) = STR(?catalogId))
    }
    """
    response = requests.post(
        endpoint, data={"query": query},
        headers={"Accept": "application/sparql-results+json"}, timeout=30,
    )
    response.raise_for_status()
    rows = [{k: v["value"] for k, v in b.items()}
            for b in response.json()["results"]["bindings"]]
    expected = {
        "https://aas.example.com/PI101": ("PI_101", "PI-1101", "XMEAS7"),
        "https://aas.example.com/FI106": ("FI_106", "FI-1101", "XMEAS6"),
        "https://aas.example.com/TI101": ("TI_101", "TI-1101", "XMEAS9"),
        "https://aas.example.com/LI101": ("LI_101", "LI-1101", "XMEAS8"),
    }
    selected = {}
    for asset_id, (dexpi_id, ecad_id, signal) in expected.items():
        matches = [row for row in rows if row.get("assetId") == asset_id
                   and row.get("dexpiLocal") == dexpi_id
                   and row.get("ecadLocal") == ecad_id
                   and row.get("signal") == signal]
        if len(matches) != 1:
            raise ValueError(
                f"Expected one exact four-domain join for {asset_id}; found {len(matches)}"
            )
        selected[asset_id] = matches[0]
    return selected


def evaluate(engineering, temporal, graph_mappings=None):
    """Supported means evidence available, not LLM answer correctness."""
    results = []
    for index, (question, sources) in enumerate(QUESTIONS, 1):
        item = {"id": f"Q{index}", "question": question, "required_sources": sources,
                "answer_correctness": "NOT_ASSESSED"}
        if index in {1, 2, 3, 6, 7, 10}:
            if graph_mappings is None:
                item["status"] = "CROSS_DOMAIN_QUERY_NOT_RUN"
                item["reason"] = "Pass --graphdb-url to verify four-domain joins."
            else:
                selected = list(graph_mappings.values())
                if index == 7:
                    selected = [graph_mappings["https://aas.example.com/PI101"]]
                if index == 10:
                    selected = [graph_mappings["https://aas.example.com/FI106"]]
                item["status"] = "EVIDENCE_AVAILABLE"
                item["evidence"] = {
                    "graphdb_verified_mappings": selected,
                    "logical_identity_scope": "ACCEPTED_LOGICAL_SIMULATION_IDENTITY",
                    "physical_installation_verified": False,
                }
                if index == 10:
                    if temporal is None:
                        item["status"] = "INCOMPLETE_TEMPORAL_EVIDENCE"
                        item["reason"] = "No TimescaleDB run supplied."
                    else:
                        item["evidence"]["temporal"] = {
                            "run_id": temporal["run_id"],
                            "signal": "XMEAS6",
                            "activation": temporal["selected_activation"],
                            "measurements": temporal["measurements"].get("XMEAS6"),
                        }
                        if not temporal["measurements"].get("XMEAS6"):
                            item["status"] = "INCOMPLETE_TEMPORAL_EVIDENCE"
        elif index in {4, 5}:
            item["status"] = "EVIDENCE_AVAILABLE"
            item["evidence"] = engineering
        elif temporal is None:
            item["status"] = "NOT_EXECUTED"
            item["reason"] = "No verified run ID and TimescaleDB connection supplied"
        elif index == 8:
            item["status"] = ("EVIDENCE_AVAILABLE" if temporal["selected_activation"]
                              else "NO_RECORDED_ACTIVATION")
            item["evidence"] = {"run_id": temporal["run_id"],
                                "activation": temporal["selected_activation"]}
        else:
            rows = temporal["measurements"]
            complete = len(rows) == 4 and all(
                row["before"] is not None and row["after"] is not None
                for row in rows.values())
            item["status"] = "EVIDENCE_AVAILABLE" if complete else "INCOMPLETE_TEMPORAL_EVIDENCE"
            item["evidence"] = {"run_id": temporal["run_id"],
                                "activation": temporal["selected_activation"],
                                "measurements": rows}
        results.append(item)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-inventory", default="examples/aas/asset_inventory_instance.json")
    parser.add_argument("--product-catalog", default="examples/aas/product_catalog_instance.json")
    parser.add_argument("--graphdb-url", default=None,
                        help="GraphDB SPARQL endpoint for verified four-domain joins")
    parser.add_argument("--run-id", help="Operator-verified UUID of a recorded simulation run")
    parser.add_argument("--output", default="reports/tep_nexus_paper_evaluation.json")
    args = parser.parse_args()
    engineering = engineering_evidence(args.asset_inventory, args.product_catalog)
    temporal = None
    if args.run_id:
        dsn = os.environ.get("TEP_TIMESCALE_DSN")
        if not dsn:
            parser.error("TEP_TIMESCALE_DSN is required when --run-id is supplied")
        temporal = temporal_evidence(dsn, args.run_id, [x[2] for x in ASSETS.values()])
    graph_mappings = verified_graphdb_mappings(args.graphdb_url) if args.graphdb_url else None
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "read_only_reference_evidence_not_automated_natural_language_scoring",
        "engineering": engineering, "temporal": temporal,
        "graphdb_verified_mappings": graph_mappings,
        "results": evaluate(engineering, temporal, graph_mappings),
        "limitations": [
            "No fault is injected by this script.",
            "Fault events record operator commands, not verified causal effects.",
            "DEXPI/ECAD joins are only validated when --graphdb-url is supplied and exact joins succeed.",
            "Product QUDT values are specifications, not verified simulation units.",
            "Product associations are not verified physical installations.",
            "Successful retrieval is not an LLM correctness score.",
        ],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved {output}; evidence-available questions: "
          f"{sum(r['status'] == 'EVIDENCE_AVAILABLE' for r in report['results'])}/10")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
