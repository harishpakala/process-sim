"""N-domain Qwen selection contract; no semantic bypass or SPARQL compilation."""
from __future__ import annotations

import json

from process_sim.dtwise.experimental_shacl_cross_domain_graph import (
    qualify_mapping_graph, validate_mapping_graph_selection,
)
from process_sim.dtwise.experimental_shacl_selection import SelectionContractError

SYSTEM_PROMPT = """You select semantic intent from SHACL-qualified N-domain candidates.
Select only supplied IDs. Do not invent domains, paths, mappings, or joins.
Result candidates describe what the question asks to return; identifier paths
are used solely to connect selected domains through approved mapping edges.
Choose the mapping edges and their owner-specific identifier paths together.
When a mapping provides approved_owner_pair_candidate_ids, select only one
of those explicitly approved endpoint ID pairs. Never combine endpoints
from different approved pairs or infer an unlisted owner-to-owner join.
If no mapping candidates remain, return unresolved with empty ID arrays.
A selected result's entity owner must be the same SHACL owner as its selected
identifier path, or connected by a supplied verified SHACL path. Matching
predicate names alone do NOT connect different owners. For example, selecting
an Equipment result does not permit an ActuatingFunction identifier path.
For every domain requested as a result, select its result owner and a matching
identifier owner. Do not add results or identifier owners merely because they
are offered. Do not automatically choose every mapping or every owner sharing
a predicate. Choose only mapping edges necessary to connect requested domains.
Respect explicit identifier constraints, including exclusions: never substitute
AssetIdentifier when the question explicitly requires ProductIdentifier only.
If no offered mapping supports the required identifier, return unresolved.
When multiple owner paths fit and the question cannot distinguish them,
return ambiguous, with empty ID arrays; do not select all alternatives.
An approved mapping does not establish instance-level identifier equality.
If no supported plan fits, return unresolved.
Return ONLY JSON with exactly:
status ("selected", "ambiguous", "unresolved"),
result_ids (array), identifier_path_ids (array), mapping_ids (array),
reason (nonempty string).
For ambiguous/unresolved all three arrays must be empty."""


def prepare_n_domain_selection(question: str, qualified_domains: dict[str, dict],
                               mappings: dict[str, dict]) -> dict:
    """Preserve all qualified result/property paths and approved mapping options."""
    if not isinstance(question, str) or not question.strip():
        raise SelectionContractError("Question must be nonempty")
    graph = qualify_mapping_graph(mappings, qualified_domains)
    results = []
    result_registry = {}
    for domain, qualified in sorted(qualified_domains.items()):
        registry = qualified["registry"]
        for candidate in qualified["prompt"]["candidates"]:
            local_id = candidate["id"]
            if local_id not in registry or registry[local_id].get("domain") != domain:
                raise SelectionContractError("Candidate and registry disagree")
            if candidate.get("kind") not in ("result", "property"):
                raise SelectionContractError("Unknown candidate kind")
            cid = f"{domain}:{local_id}"
            if cid in result_registry:
                raise SelectionContractError("Duplicate scoped result ID")
            results.append({"id": cid, "domain": domain,
                            "kind": candidate["kind"], "path": candidate["path"]})
            result_registry[cid] = registry[local_id]
        if {c["id"] for c in qualified["prompt"]["candidates"]} != set(registry):
            raise SelectionContractError("Candidate IDs and registry disagree")
    return {
        "prompt": {
            "question": question,
            "result_candidates": results,
            "identifier_path_candidates": graph["identifier_path_candidates"],
            "mapping_candidates": graph["mapping_candidates"],
        },
        "result_registry": result_registry,
        "mapping_registry": mappings,
    }


def validate_n_domain_selection(raw: str | dict, prepared: dict) -> dict:
    """Check response shape, membership, and selected mapping graph."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SelectionContractError("Invalid JSON response") from exc
    fields = {"status", "result_ids", "identifier_path_ids", "mapping_ids", "reason"}
    if not isinstance(raw, dict) or set(raw) != fields:
        raise SelectionContractError("Invalid N-domain response fields")
    status, reason = raw["status"], raw["reason"]
    if status not in ("selected", "ambiguous", "unresolved"):
        raise SelectionContractError("Invalid selection status")
    if not isinstance(reason, str) or not reason.strip():
        raise SelectionContractError("Selection reason is required")
    for field in ("result_ids", "identifier_path_ids", "mapping_ids"):
        ids = raw[field]
        if (not isinstance(ids, list) or any(not isinstance(x, str) for x in ids)
                or len(ids) != len(set(ids))):
            raise SelectionContractError(f"Invalid {field}")
    if status != "selected":
        if any(raw[k] for k in ("result_ids", "identifier_path_ids", "mapping_ids")):
            raise SelectionContractError("Uncertain selection must not contain IDs")
        return {**raw, "reason": reason.strip()}
    if not raw["result_ids"] or not raw["identifier_path_ids"] or not raw["mapping_ids"]:
        raise SelectionContractError("Selected N-domain plan requires all ID groups")
    prompt = prepared["prompt"]
    results = {c["id"]: c for c in prompt["result_candidates"]}
    if any(cid not in results or cid not in prepared["result_registry"]
           for cid in raw["result_ids"]):
        raise SelectionContractError("Unknown result candidate ID")
    validate_mapping_graph_selection(
        raw["mapping_ids"], raw["identifier_path_ids"],
        {"identifier_path_candidates": prompt["identifier_path_candidates"],
         "mapping_candidates": prompt["mapping_candidates"]},
        prepared["mapping_registry"],
    )
    selected_domains = {
        d for edge in prompt["mapping_candidates"] if edge["id"] in raw["mapping_ids"]
        for d in (edge["left_domain"], edge["right_domain"])
    }
    if any(results[cid]["domain"] not in selected_domains for cid in raw["result_ids"]):
        raise SelectionContractError("Result domain is outside selected mapping graph")
    from process_sim.dtwise.experimental_shacl_n_domain_topology import validate_selected_topology
    validate_selected_topology(raw, prepared)
    return {**raw, "reason": reason.strip()}


def select_n_domain_with_ollama(prepared: dict, *, model="qwen2.5-coder:7b",
                               endpoint="http://127.0.0.1:11434", transport=None) -> dict:
    """One Qwen call; independently validate its answer. No compilation."""
    from process_sim.dtwise.experimental_shacl_ollama import ollama_select
    raw = ollama_select(prepared["prompt"], model=model, endpoint=endpoint,
                        transport=transport, system_prompt=SYSTEM_PROMPT)
    return validate_n_domain_selection(raw, prepared)
