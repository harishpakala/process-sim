"""Resolve contract bindings against the existing ONTO NEXUS SHACL registry.

AAS template IDs and RDF paths are checked against lifted registry records.
Class/field selections remain explicit: the registry cannot infer business
roles (asset vs canonical product) or canonical identity automatically.
"""

# Created: 2026-10-31
# Author: Harish
from .compiler import CompilationError, _iri


def bindings_from_registry(registry, selections):
    """selections: {templateId: {class: IRI, fields: {alias: IRI}}}.

    Only template IDs/classes/paths present in the registry are accepted.
    Does not claim that any live graph or evidence scope is complete.
    """
    domains = {d["templateId"]: d for d in registry["domains"]}
    result = {"templates": {}}
    for template_id, selected in selections.items():
        if template_id not in domains:
            raise CompilationError(f"Template absent from ONTO NEXUS registry: {template_id}")
        domain = domains[template_id]
        classes = {
            c if isinstance(c, str) else c.get("iri")
            for c in (domain.get("instanceClasses", []) + domain.get("templateClasses", []))
        }
        selected_class = str(_iri(selected["class"], "selected class"))
        if selected_class not in classes:
            raise CompilationError(f"Class absent from lifted registry: {selected_class}")
        allowed_paths = {p["predicate"] for p in domain.get("shaclPaths", [])}
        for field, path in selected["fields"].items():
            _iri(path, f"field {field}")
            if path not in allowed_paths:
                raise CompilationError(f"Path absent from lifted SHACL: {field} -> {path}")
        result["templates"][template_id] = {
            "class": selected_class,
            "fields": dict(selected["fields"]),
            "complete": False,
        }
    return result
