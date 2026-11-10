#!/usr/bin/env python3
"""Evaluate Q1-Q13 together with source-backed, evidence-conditioned Ollama QA.

Run from the process-sim repository root. Existing ten-question records are
left unchanged. This does NOT execute the live VTKG pipeline or auto-grade.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="Recorded simulation run UUID")
    parser.add_argument("--only-q13", action="store_true", help="Run Q13-v2 only; skip Q1-Q12 evidence and model calls")
    parser.add_argument("--graphdb-url", default="http://localhost:7200/repositories/AAS")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--start-seconds", type=float, default=0.0)
    parser.add_argument("--end-seconds", type=float, default=60.0)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output-dir", default="reports/evaluation_13_v2_grounded")
    args = parser.parse_args()
    if not 0 <= args.start_seconds <= args.end_seconds or not 1 <= args.limit <= 5000:
        parser.error("Require 0 <= start <= end and 1 <= limit <= 5000.")
    dsn = os.getenv("TEP_TIMESCALE_DSN")
    if not dsn:
        parser.error("TEP_TIMESCALE_DSN must be set locally; do not commit credentials.")

    output = ROOT / args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    import psycopg
    qa = load_module("scripts/tep_nexus_e4e_ollama_qa.py", "ollama_qa_12")
    q11 = q12 = None
    graph_error = None
    rows = []
    if not args.only_q13:
        evaluator = load_module("scripts/tep_nexus_paper_evaluation.py", "paper_eval_12")
        engineering = evaluator.engineering_evidence(
            str(ROOT / "examples/aas/asset_inventory_instance.json"),
            str(ROOT / "examples/aas/product_catalog_instance.json"))
        temporal = evaluator.temporal_evidence(
            dsn, args.run_id, [item[2] for item in evaluator.ASSETS.values()])
        graph_error = None
        try:
            graph = evaluator.verified_graphdb_mappings(args.graphdb_url)
        except ValueError as exc:
            graph = None
            graph_error = str(exc)
            print("WARNING: GraphDB four-domain verification failed: " + graph_error,
                  flush=True)
            print("Affected questions will be marked GRAPHDB_VERIFICATION_FAILED, "
                  "not PASS.", flush=True)
        evidence_rows = evaluator.evaluate(engineering, temporal, graph)
        questions_path = ROOT / "docs/e4e_tests/revised_questions.json"
        questions = json.loads(questions_path.read_text(encoding="utf-8"))["questions"]
        if [q["id"] for q in questions] != [f"Q{i}" for i in range(1, 11)]:
            raise RuntimeError("Expected exactly the revised independent Q1-Q10 question set.")
        rows = []
        for question, record in zip(questions, evidence_rows):
            status = record["status"]
            reason = record.get("reason")
            if graph_error and status == "CROSS_DOMAIN_QUERY_NOT_RUN":
                status = "GRAPHDB_VERIFICATION_FAILED"
                reason = graph_error
            rows.append({
                **question,
                "required_sources": record["required_sources"],
                "evidence_status": status,
                "evidence_reason": reason,
                "evidence": record.get("evidence"),
            })
        evidence_file = output / "evidence/revised/evidence_and_assessment_template.json"
        evidence_file.parent.mkdir(parents=True, exist_ok=True)
        evidence_file.write_text(json.dumps({
            "run_id": args.run_id,
            "version": "revised",
            "assessment_status": "NOT_ASSESSED",
            "graphdb_verification_error": graph_error,
            "results": rows,
        }, indent=2, default=str) + "\n", encoding="utf-8")

        engineering = evaluator.engineering_evidence(
            str(ROOT / "examples/aas/asset_inventory_instance.json"),
            str(ROOT / "examples/aas/product_catalog_instance.json"))
        temperature = engineering["temperature"]
        if temperature["equipment_tag"] != "TI-1101" or temperature["signal"] != "XMEAS9":
            raise RuntimeError("TI-1101 to XMEAS9 mapping differs from the test fixture.")

        q11 = {
            "source": "AAS AssetInventory and ProductCatalog instances",
            "asset_id": temperature.get("asset_id"),
            "equipment_tag": temperature.get("equipment_tag"),
            "product_uri": temperature.get("product_uri"),
            "product_key": temperature.get("product_key"),
            "eclass_class": temperature.get("eclass_class"),
            "eclass_irdi": temperature.get("eclass_irdi"),
            "eclass_verification": temperature.get("eclass_verification"),
            "product_selection_status": temperature.get("product_selection_status"),
            "installation_verification": temperature.get("installation_verification"),
        }

        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.transaction():
                conn.execute("SET TRANSACTION READ ONLY")
                samples = conn.execute("""
                    SELECT simulation_time_hours, value, observed_at
                    FROM public.signal_samples
                    WHERE run_id = %s::uuid AND signal_id = %s
                      AND simulation_time_hours >= %s
                      AND simulation_time_hours <= %s
                    ORDER BY simulation_time_hours, observed_at
                    LIMIT %s
                """, (args.run_id, "XMEAS9", args.start_seconds / 3600,
                      args.end_seconds / 3600, args.limit + 1)).fetchall()
        truncated = len(samples) > args.limit
        q12 = {
            "source": "TimescaleDB public.signal_samples (read-only)",
            "mapping_source": "AAS AssetInventory instance",
            "asset_id": temperature.get("asset_id"),
            "equipment_tag": "TI-1101",
            "signal": "XMEAS9",
            "run_id": args.run_id,
            "interval_seconds_inclusive": [args.start_seconds, args.end_seconds],
            "truncated": truncated,
            "observations": [
                {"simulation_seconds": float(t) * 3600, "value": float(v),
                 "observed_at": ts.isoformat()}
                for t, v, ts in samples[:args.limit]
            ],
            "qualification": "Direct historian evidence, not VTKG-to-SQL equivalence.",
        }
        rows += [
            {"id": "Q11", "question":
             "What ECLASS IRDI is associated with the product candidate linked to reactor temperature instrument TI-1101?",
             "evidence_status": "EVIDENCE_AVAILABLE" if q11["eclass_irdi"] else "NO_EVIDENCE",
             "evidence": q11},
            {"id": "Q12", "question":
             f"What temperature-signal observations were recorded for reactor temperature instrument TI-1101 (XMEAS9) between simulation time {args.start_seconds:g} and {args.end_seconds:g} seconds in the selected simulation run?",
             "evidence_status": "EVIDENCE_AVAILABLE" if q12["observations"] else "NO_EVIDENCE",
             "evidence": q12},
        ]

    # Q13 is appended without altering the existing Q1-Q12 wording or evidence.
    # Its historian run/window are fixed by the published Q13 question.
    q13_run = "10cfb1d1-2984-4932-8207-dc430ed60c2b"
    q13_asset = "https://aas.example.com/TI101"
    q13_product = "https://example.org/product-types/IFM_TA1101"
    q13_queries = {
        "canonical_asset_identifiers": """
            SELECT ?subject ?predicate ?value WHERE {
              ?subject ?predicate ?value .
              FILTER(CONTAINS(STR(?predicate), "AssetIdentifier"))
              FILTER(STR(?value) = "https://aas.example.com/TI101")
            } ORDER BY ?subject ?predicate LIMIT 100
        """,
        "product_and_signal_references": """
            SELECT ?subject ?predicate ?value WHERE {
              ?subject ?predicate ?value .
              FILTER(
                CONTAINS(STR(?predicate), "ProductIdentifier") ||
                CONTAINS(STR(?predicate), "ProductReference") ||
                CONTAINS(STR(?predicate), "EngineeringFunctionReference") ||
                CONTAINS(STR(?predicate), "SignalName")
              )
              FILTER(
                CONTAINS(STR(?value), "IFM_TA1101") ||
                CONTAINS(STR(?value), "XMEAS9") ||
                STR(?value) = "https://aas.example.com/TI101"
              )
            } ORDER BY ?subject ?predicate LIMIT 100
        """,
        "opcua_mapping_provenance": """
            SELECT ?subject ?predicate ?value WHERE {
              ?subject <https://example.org/opcuaconnectivity/hasEngineeringFunctionReference>
                "https://aas.example.com/TI101" .
              ?subject ?predicate ?value .
            } ORDER BY ?predicate LIMIT 100
        """,
    }
    q13 = {
        "source": "Live GraphDB SPARQL and TimescaleDB read-only queries",
        "asset_identifier": q13_asset,
        "product_candidate_identifier": q13_product,
        "run_id": q13_run,
        "signal": "XMEAS9",
        "interval_seconds_inclusive": [0, 600],
        "graphdb": {},
        "graphdb_errors": {},
        "historian_error": None,
        "observations": [],
        "observations_truncated": False,
        "mapping_qualification": (
            "OPC UA engineering match is provisional; live OPC UA binding and "
            "physical product installation are not verified."
        ),
    }
    import requests
    for name, sparql in q13_queries.items():
        try:
            response = requests.post(
                args.graphdb_url, data={"query": sparql},
                headers={"Accept": "application/sparql-results+json"},
                timeout=30)
            response.raise_for_status()
            q13["graphdb"][name] = [
                {key: val.get("value") for key, val in binding.items()}
                for binding in response.json()["results"]["bindings"]
            ]
        except (requests.RequestException, ValueError, KeyError) as exc:
            q13["graphdb_errors"][name] = f"{type(exc).__name__}: {exc}"

    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            with conn.transaction():
                conn.execute("SET TRANSACTION READ ONLY")
                q13_samples = conn.execute("""
                    SELECT simulation_time_hours, value, observed_at
                    FROM public.signal_samples
                    WHERE run_id = %s::uuid AND signal_id = %s
                      AND simulation_time_hours >= 0
                      AND simulation_time_hours <= %s
                    ORDER BY simulation_time_hours, observed_at
                    LIMIT %s
                """, (q13_run, "XMEAS9", 600.0 / 3600.0, args.limit + 1)).fetchall()
        q13["observations_truncated"] = len(q13_samples) > args.limit
        q13["observations"] = [
            {"simulation_seconds": float(t) * 3600, "value": float(v),
             "observed_at": ts.isoformat() if ts is not None else None}
            for t, v, ts in q13_samples[:args.limit]
        ]
    except (psycopg.Error, ValueError, TypeError) as exc:
        q13["historian_error"] = f"{type(exc).__name__}: {exc}"

    q13_complete = (
        not q13["graphdb_errors"]
        and all(q13["graphdb"].get(name) for name in q13_queries)
        and bool(q13["observations"])
        and not q13["observations_truncated"]
    )
    rows.append({
        "id": "Q13",
        "question": (
            "Using the supplied GraphDB and TimescaleDB evidence, trace the "
            "reactor-temperature measurement across the six AAS information models. "
            "Answer in order: (1) DEXPI: engineering function and source tag; "
            "(2) ECAD: electrical device and tag; (3) Engineering BOM: associated "
            "BOM items; (4) AssetInventory: logical asset and shared AssetIdentifier; "
            "(5) ProductCatalog: associated product candidate and whether physical "
            "installation is verified; (6) OPC UA Connectivity: operational signal, "
            "engineering reference, OPC UA node and mapping status; "
            "(7) TimescaleDB: for simulation run "
            "10cfb1d1-2984-4932-8207-dc430ed60c2b, report the number of XMEAS9 "
            "observations between simulation seconds 0 and 600, first and last "
            "observation times, and their recorded values. Finish with a brief "
            "summary of how the models are linked through the shared "
            "AssetIdentifier, and explicitly identify provisional or unverified "
            "mappings. Use only supplied evidence; do not invent missing "
            "relationships, product-installation confirmations, or live OPC UA "
            "verification."
        ),
        "evidence_status": (
            "EVIDENCE_AVAILABLE" if q13_complete else "INCOMPLETE_EVIDENCE"
        ),
        "evidence": q13,
    })

    grounding_rules = (
        "Answer the question using only the supplied JSON evidence. "
        "Report explicit identifiers, mappings, values, and timestamps directly; "
        "do not downgrade an explicit canonical assetId or GraphDB mapping to a guess. "
        "A verified logical mapping does NOT verify physical installation or product "
        "selection: preserve those separate qualifications. "
        "An operator injection command is a recorded request, not proof that a fault "
        "became active; do not describe samples at the command time as post-fault. "
        "For temporal queries, distinguish simulation_seconds from observed_at "
        "(wall-clock record time); 30 and 30.0 seconds denote the same instant. "
        "Floating-point roundoff (for example 27.000000000000004) is not itself "
        "a timing discrepancy. Do not claim timing discrepancies, physical "
        "installation, measurement units, causal effects, or missing mappings "
        "without supporting evidence. If evidence is genuinely missing, identify "
        "the specific missing field. Answer concisely and completely."
    )
    destination = output / ("answers_q13_v2_only.json" if args.only_q13 else "answers_13_v2.json")
    results = []
    for row in rows:
        evidence = row.get("evidence")
        # Q13-v2: give the LLM a compact evidence digest, not 207 raw rows.
        # The full unmodified Q13 evidence remains in q13_evidence in the output.
        prompt_evidence = evidence
        if row["id"] == "Q13":
            compact_graph = {}
            for group, triples in q13["graphdb"].items():
                compact_graph[group] = [
                    {"subject": t["subject"].rsplit("/", 1)[-1],
                     "predicate": t["predicate"].rsplit("/", 1)[-1].rsplit("#", 1)[-1],
                     "value": t["value"]}
                    for t in triples
                    if group != "opcua_mapping_provenance"
                    or t["predicate"].startswith("https://example.org/opcuaconnectivity/")
                ]
            observations = q13["observations"]
            prompt_evidence = {
                "source": q13["source"],
                "asset_identifier": q13["asset_identifier"],
                "product_candidate_identifier": q13["product_candidate_identifier"],
                "graphdb": compact_graph,
                "graphdb_errors": q13["graphdb_errors"],
                "historian": {
                    "run_id": q13["run_id"], "signal": q13["signal"],
                    "interval_seconds_inclusive": q13["interval_seconds_inclusive"],
                    "returned_observation_count": len(observations),
                    "truncated": q13["observations_truncated"],
                    "error": q13["historian_error"],
                    "first_observation": observations[0] if observations else None,
                    "last_observation": observations[-1] if observations else None,
                },
                "mapping_qualification": q13["mapping_qualification"],
                "evidence_limitations": (
                    "GraphDB subject identifiers are abbreviated suffixes; "
                    "source model and item identity must be supported by returned "
                    "predicates/subjects, not inferred from a candidate product. "
                    "Missing engineering tag fields must be reported as missing."
                ),
            }
        prompt = ("Question:\n" + row["question"] +
                  "\n\nEvidence from a read-only snapshot (JSON):\n" +
                  json.dumps(prompt_evidence, indent=2, ensure_ascii=False, default=str) +
                  "\n\nGrounding instructions:\n" + grounding_rules)
        entry = {
            "id": row["id"], "question": row["question"],
            "question_version": "Q13-v2" if row["id"] == "Q13" else "unchanged",
            "evidence_status": row.get("evidence_status"),
            "evidence_sha256": hashlib.sha256(
                json.dumps(evidence, sort_keys=True, default=str).encode()).hexdigest(),
            "answer_text": None, "model_metadata": None,
            "manual_assessment": None, "assessment_justification": None, "error": None,
        }
        try:
            entry["answer_text"], entry["model_metadata"] = qa.request_ollama(
                args.ollama_url, args.model, prompt, args.timeout)
            print(f'{row["id"]}: answer saved', flush=True)
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            print(f'{row["id"]}: ERROR: {exc}', flush=True)
        results.append(entry)
        destination.write_text(json.dumps({
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": args.run_id,
            "model_requested": args.model,
            "grounding_instructions": grounding_rules,
            "method": "evidence_conditioned_ollama_qa_not_live_vtkg_execution",
            "assessment_status": "NOT_MANUALLY_ASSESSED",
            "q11_evidence": q11, "q12_evidence": q12, "q13_evidence": q13,
            "only_q13": args.only_q13,
            "q13_prompt_evidence": prompt_evidence if row["id"] == "Q13" else None,
            "graphdb_verification_error": graph_error,
            "results": results,
        }, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(f"Saved {destination}; {len(results)} questions; no automatic grades.")


if __name__ == "__main__":
    main()
