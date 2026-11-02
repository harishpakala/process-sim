#!/usr/bin/env python3
"""TEP NEXUS paper Q1-Q10 planner; read-only, evidence grounded.

Uses an existing paper-evaluation JSON report. Optional GraphDB probing
discovers explicit RDF edges; it never equates tags by string similarity.
Ollama selects a fixed question ID and explains only supplied evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

QUESTIONS = [
    "Which instruments are associated with the reactor?",
    "What are their electrical references?",
    "What are their asset IDs and signal references?",
    "Which products and manufacturers are associated with these assets?",
    "What are their ECLASS and QUDT attributes?",
    "Which asset identifiers link the engineering representations?",
    "What engineering information is available for PI-1101?",
    "Which fault was activated, and when?",
    "What were the four sensor values before and after activation?",
    "What engineering and operational evidence is available for FI-1101?",
]
TAGS = ("PI-1101", "FI-1101", "TI-1101", "LI-1101")
MAX_GRAPH_ROWS = 200
PROMPT_VERSION = "E4C_V1_EXPLICIT_FIELD_GROUNDING"
ANSWER_SYSTEM_PROMPT = """You are TEP NEXUS, a read-only engineering evidence retrieval assistant.
Answer the supplied question using ONLY the supplied evidence. Do not use external
knowledge, reference answers, or inferred engineering relationships.

Interpret the evidence fields precisely:
- dexpiLocal is a DEXPI instrument reference.
- ecadLocal is an electrical engineering reference; it is NOT a signal.
- assetId is a canonical logical simulation asset identifier.
- signal is an operational measurement reference (for example, XMEAS6).
- productId or product_uri is an associated product candidate, not installed hardware.

Answer ALL requested parts and preserve the exact evidence values.
For multi-instrument questions, include every instrument represented in evidence.
For product questions, pair each asset/tag with its manufacturer and product.
For ECLASS and QUDT questions, include every asset's ECLASS identifier and its
QUDT product specification attributes; do not treat these as simulation units.
For fault events, give the fault ID, operator action, simulation_seconds and,
when relevant, observed_at as a separate wall-clock timestamp.
For before/after measurements, give each signal's values and simulation times.
For combined engineering and operational questions, include identifiers,
the operational signal, and the actual numerical samples where available.
Do not infer equipment types from product names. Never assert a physical
installation, verified ECLASS release, causal fault effect, or measurement units
that the evidence does not establish. If something is missing, say so.
Return JSON with EXACTLY two keys: answer (string) and limitations (array of strings).
Put requested factual content in answer, NOT in limitations.
"""
ANSWER_PROMPT_SHA256 = hashlib.sha256(ANSWER_SYSTEM_PROMPT.encode("utf-8")).hexdigest()


def graphdb_probe(endpoint, timeout=15):
    """Inspect exact RDF IRI edges and labels, not inferred engineering joins."""
    import requests
    query = """
    SELECT ?s ?p ?o WHERE {
      ?s ?p ?o .
      FILTER(isIRI(?s) && isIRI(?p) && isIRI(?o))
    } LIMIT 200
    """
    r = requests.post(endpoint, data={"query": query},
                      headers={"Accept": "application/sparql-results+json"},
                      timeout=timeout)
    r.raise_for_status()
    bindings = r.json()["results"]["bindings"]
    return [{"subject": b["s"]["value"], "predicate": b["p"]["value"],
             "object": b["o"]["value"]} for b in bindings]


def ollama_json(url, model, system, payload):
    import requests
    r = requests.post(url.rstrip("/") + "/api/chat", json={
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": 0},
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": json.dumps(payload)}]},
        timeout=180)
    r.raise_for_status()
    result = json.loads(r.json()["message"]["content"])
    if not isinstance(result, dict):
        raise ValueError("Ollama response must be a JSON object")
    return result


def validate_selection(raw, question_id):
    if set(raw) != {"question_id"} or raw["question_id"] != question_id:
        raise ValueError("Planner did not return the exact allowed question ID")
    return {"question_id": question_id, "strategy": "fixed_question_registry"}


def answer_for(item, engineering, temporal, graph):
    """Deterministic fallback: no unsupported assertion or invented answer."""
    status = item["status"]
    if status != "EVIDENCE_AVAILABLE":
        return {"answer": "Insufficient verified evidence to answer this question.",
                "limitations": [item.get("reason", status)]}
    i = int(item["id"][1:])
    if i in {1, 2, 3, 6, 7, 10}:
        mappings = item["evidence"]["graphdb_verified_mappings"]
        if i == 1:
            text = "; ".join(f"{m['dexpiLocal']} ({m['assetId']})" for m in mappings)
        elif i == 2:
            text = "; ".join(f"{m['dexpiLocal']} -> ECAD {m['ecadLocal']}" for m in mappings)
        elif i == 3:
            text = "; ".join(f"{m['assetId']} -> {m['signal']}" for m in mappings)
        elif i == 6:
            text = "; ".join(
                f"{m['dexpiLocal']} / {m['ecadLocal']} / AssetInventory: {m['assetId']}"
                for m in mappings
            )
        elif i == 7:
            m = mappings[0]
            text = (f"{m['assetId']}: DEXPI {m['dexpiLocal']}, ECAD {m['ecadLocal']}, "
                    f"operational signal {m['signal']}, product {m['productId']}, "
                    f"ECLASS {m.get('eclassCode', 'not available')}")
        else:
            m = mappings[0]
            temporal = item["evidence"].get("temporal", {})
            samples = temporal.get("measurements") or {}
            text = (f"{m['assetId']}: DEXPI {m['dexpiLocal']}, ECAD {m['ecadLocal']}, "
                    f"signal {m['signal']}, product {m['productId']}, "
                    f"run {temporal.get('run_id', 'not available')}; "
                    f"activation-adjacent samples: {json.dumps(samples, sort_keys=True)}")
    elif i == 4:
        text = "; ".join(f"{v['equipment_tag']}: {v.get('manufacturer') or 'unknown'} "
                         f"({v.get('product_key') or 'unknown'})"
                         for v in engineering.values())
    elif i == 5:
        text = "; ".join(f"{v['equipment_tag']}: ECLASS {v.get('eclass_irdi')}; "
                         f"QUDT product attributes {json.dumps(v.get('qudt_product_specification', {}), sort_keys=True)}"
                         for v in engineering.values())
    elif i == 8:
        event = item["evidence"].get("activation")
        text = (f"Recorded operator command {event['action']} for fault {event['fault_id']} "
                f"at simulation time {event['simulation_seconds']:.3f} seconds."
                if event else "No recorded fault command.")
    elif i == 9:
        ev = item["evidence"]
        text = "; ".join(f"{signal}: before={row['before']['value']:.6g} "
                         f"at {row['before']['simulation_seconds']:.3f}s; "
                         f"after={row['after']['value']:.6g} "
                         f"at {row['after']['simulation_seconds']:.3f}s"
                         for signal, row in ev["measurements"].items())
    else:
        text = "Insufficient verified evidence to answer this question."
    return {"answer": text, "limitations": [
        "Retrieval is not proof of physical installation, causality or LLM answer correctness.",
        "Four-domain joins are accepted logical simulation mappings, not physical installation verification."
    ]}


def run(report, graph_edges=None, ollama_url=None, model="llama3.1:8b"):
    results = []
    source = {x["id"]: x for x in report["results"]}
    if len(source) != 10 or any(f"Q{i}" not in source for i in range(1, 11)):
        raise ValueError("Evidence must contain Q1-Q10")
    for index, question in enumerate(QUESTIONS, 1):
        qid = f"Q{index}"
        item = source[qid]
        if item["question"] != question:
            raise ValueError(
                f"Question registry mismatch for {qid}; regenerate evidence with the updated evaluator"
            )
        entry = {"id": qid, "question": question, "source_status": item["status"],
                 "validated_plan": {"question_id": qid, "strategy": "fixed_question_registry"},
                 "graphdb_probe_status": "IRI_EDGES_INSPECTED_NOT_JOIN_VALIDATED" if graph_edges is not None else "NOT_RUN",
                 "answer_validation": "NOT_AUTOMATICALLY_VERIFIED"}
        evidence = item.get("evidence")
        entry["evidence"] = evidence
        fallback = answer_for(item, report["engineering"], report.get("temporal"), graph_edges)
        entry["reference_answer"] = fallback
        if ollama_url:
            try:
                raw = ollama_json(ollama_url, model,
                    "You are a constrained planner. Return only JSON with exactly one key question_id. "
                    "Copy the supplied allowed_question_id verbatim; never produce SQL or SPARQL.",
                    {"allowed_question_id": qid, "question": question})
                entry["raw_plan"] = raw
                entry["validated_plan"] = validate_selection(raw, qid)
                if item["status"] == "EVIDENCE_AVAILABLE":
                    answer = ollama_json(
                        ollama_url, model, ANSWER_SYSTEM_PROMPT,
                        {"question": question, "evidence": evidence},
                    )
                    if set(answer) != {"answer", "limitations"} or not isinstance(answer["answer"], str) or not isinstance(answer["limitations"], list) or not all(isinstance(x, str) for x in answer["limitations"]):
                        raise ValueError("Invalid Ollama answer format")
                    entry["ollama_answer"] = answer
                else:
                    entry["ollama_answer"] = fallback
            except Exception as exc:
                entry["ollama_error"] = str(exc)
                entry["ollama_answer"] = None
        results.append(entry)
    return {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_run_id": (report.get("temporal") or {}).get("run_id"),
            "graphdb_probe_edge_count": len(graph_edges) if graph_edges is not None else None,
            "graphdb_probe_note": "Generic bounded RDF IRI-edge inventory; not a validated DEXPI/ECAD/BOM join.",
            "ollama_model": model if ollama_url else None,
            "prompt_version": PROMPT_VERSION if ollama_url else None,
            "prompt_sha256": ANSWER_PROMPT_SHA256 if ollama_url else None,
            "prompt_hash_algorithm": "sha256" if ollama_url else None,
            "scope": "Q1-Q10 fixed-registry planner with evidence-grounded responses; correctness unassessed",
            "results": results}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", default="reports/tep_nexus_paper_evaluation.json")
    p.add_argument("--graphdb-url", default=None,
                   help="Optional read-only GraphDB IRI-edge probe")
    p.add_argument("--ollama-url", default=None,
                   help="Optional Ollama planner and answer generation")
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--output", default="reports/tep_nexus_paper_queries.json")
    a = p.parse_args()
    report = json.loads(Path(a.evidence).read_text(encoding="utf-8-sig"))
    if len(report.get("results", [])) != 10:
        p.error("Evidence report must contain Q1-Q10")
    graph = graphdb_probe(a.graphdb_url) if a.graphdb_url else None
    result = run(report, graph, a.ollama_url, a.model)
    result["answer_generation_mode"] = "BLIND_EVIDENCE_ONLY" if a.ollama_url else "NO_LLM"
    path = Path(a.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Saved {path}; {len(result['results'])} questions; "
          f"LLM correctness remains NOT_AUTOMATICALLY_VERIFIED")


if __name__ == "__main__":
    main()
