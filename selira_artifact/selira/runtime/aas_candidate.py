"""Stage bounded AAS element modifications without persistence."""
from copy import deepcopy
from dataclasses import dataclass
from rdflib import Graph
from .aas_messages import AASChangeRequest
from .semantic_lifting import SemanticLiftingAdapter


@dataclass
class CandidateState:
    document: dict
    previous_graph: Graph
    candidate_graph: Graph
    additions: Graph
    deletions: Graph


def stage_change(current_document: dict, change: AASChangeRequest,
                 adapter: SemanticLiftingAdapter) -> CandidateState:
    if current_document.get("id") != change.domain.submodel_id:
        raise ValueError("Submodel identity mismatch")
    if adapter.domain.casefold() != change.domain.name.casefold():
        raise ValueError("Domain mismatch")
    if change.domain.semantic_id is not None:
        keys = (current_document.get("semanticId") or {}).get("keys", [])
        if len(keys) != 1 or keys[0].get("value") != change.domain.semantic_id:
            raise ValueError("Submodel semantic identity mismatch")
    previous = adapter.lift_instance(current_document)
    document = deepcopy(current_document)
    parts = change.operation.id_short_path.split(".")
    if any(not p or "[" in p or "]" in p for p in parts):
        raise ValueError("Only named collection paths are supported")
    elements = document.get("submodelElements")
    if elements is None:
        elements = document["submodelElements"] = []
    for part in parts[:-1]:
        matches = [e for e in elements if e.get("idShort") == part]
        if len(matches) != 1 or matches[0].get("modelType") != "SubmodelElementCollection":
            raise ValueError("Parent collection not found or ambiguous")
        parent = matches[0]
        if parent.get("value") is None:
            parent["value"] = []
        elements = parent["value"]
    indices = [i for i, e in enumerate(elements) if e.get("idShort") == parts[-1]]
    operation = change.operation.type
    if operation != "DELETE":
        payload = deepcopy(change.payload)
        if payload.get("idShort") != parts[-1]:
            raise ValueError("Payload idShort must match target path")
    if operation == "CREATE":
        if indices:
            raise ValueError("Target already exists")
        elements.append(payload)
    else:
        if len(indices) != 1:
            raise ValueError("Target not found or ambiguous")
        if operation == "DELETE":
            del elements[indices[0]]
        else:
            elements[indices[0]] = payload
    candidate = adapter.lift_instance(document)
    return CandidateState(document, previous, candidate,
                          candidate - previous, previous - candidate)
