"""Build planner vocabulary from the same AAS sources and lifting conventions.

No GraphDB dependency; this is a declaration catalog, not a claim that RDF is loaded.
"""

# Created: 2026-10-23
# Author: Harish
from __future__ import annotations

import json
from pathlib import Path

from semantic.config import TARGETS
from semantic.ontoutils import semanticDict

AAS = str(semanticDict["AAS"])

def _concept(element):
    for qualifier in element.get("qualifiers") or []:
        if str(qualifier.get("type", "")).lower() in ("ontoconcept", "ontologyconcept"):
            return qualifier.get("value")
    return None

def build_registry(*, targets=None):
    """Read registered AAS templates and instances; mirror lifting predicate rules."""
    targets = TARGETS if targets is None else targets
    domains = []
    for domain, template_path, instance_path in targets:
        template = json.loads(Path(template_path).read_text(encoding="utf-8"))
        instance = json.loads(Path(instance_path).read_text(encoding="utf-8"))
        namespace = str(semanticDict[domain.upper()])
        predicates = {}
        classes = set()
        def walk(elements, *, source, parent=""):
            for element in elements or []:
                kind = element.get("modelType")
                short = element.get("idShort")
                if not short:
                    continue
                path = f"{parent}.{short}" if parent else short
                if kind == "SubmodelElementCollection":
                    concept = _concept(element) if source == "instance" else None
                    name = concept or short
                    uri = namespace + "has" + name
                    predicates.setdefault(uri, {"iri": uri, "sources": [], "paths": [], "kind": "object"})
                    entry = predicates[uri]
                    if source not in entry["sources"]:
                        entry["sources"].append(source)
                    if path not in entry["paths"]:
                        entry["paths"].append(path)
                    if concept:
                        classes.add(namespace + concept)
                    walk(element.get("value"), source=source, parent=path)
                elif kind in ("Property", "Range", "RelationshipElement"):
                    # Mirrors lift_property/lift_range/lift_relationship in the source.
                    uri = namespace + "has" + short
                    pred_kind = "literal" if kind == "Property" else "object"
                    entry = predicates.setdefault(uri, {"iri": uri, "sources": [], "paths": [], "kind": pred_kind})
                    if source not in entry["sources"]:
                        entry["sources"].append(source)
                    if path not in entry["paths"]:
                        entry["paths"].append(path)
                    if source == "template":
                        for q in element.get("qualifiers") or []:
                            if q.get("type") == "Cardinality":
                                entry["cardinality"] = q.get("value")
                    if kind == "RelationshipElement":
                        entry["relationshipRepresentation"] = "reified_aas_first_second"
        walk(template.get("submodelElements"), source="template")
        walk(instance.get("submodelElements"), source="instance")
        domains.append({"domain": domain, "namespace": namespace,
                        "template": str(template_path), "instance": str(instance_path),
                        "classes": sorted(classes),
                        "predicates": sorted(predicates.values(), key=lambda x: x["iri"])})
    return {"domains": domains, "aasNamespace": AAS,
            "note": "Derived from configured AAS JSON and lifting conventions. Not a complete OWL ontology or proof of GraphDB ingestion."}

def planner_context(registry, *, max_predicates=240):
    """Compact, deterministic context; reject truncation rather than silently hiding schema."""
    items = [(d["domain"], p["iri"], p["kind"]) for d in registry["domains"] for p in d["predicates"]]
    if len(items) > max_predicates:
        raise ValueError("Registry exceeds planner context budget; scope domains explicitly")
    return {"predicates": items,
            "classes": [c for d in registry["domains"] for c in d["classes"]],
            "aas": registry["aasNamespace"],
            "note": registry["note"]}
