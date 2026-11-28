"""Read-only bridge to the existing ONTO:NEXUS lifting package.

The host semantic package must be importable. No GraphDB writes, no
alternative mapping rules, and no implicit evidence attestations.
"""
from copy import deepcopy

from rdflib import Graph


def _parse_submodel(document):
    from aas_core3_1.jsonization import submodel_from_jsonable
    from aas_core3_1 import types

    submodel = submodel_from_jsonable(deepcopy(document))
    supported = (types.Property, types.Range, types.SubmodelElementCollection,
                 types.RelationshipElement)

    def check(elements):
        names = set()
        for element in elements or []:
            if type(element) not in supported:
                raise ValueError(f"Unsupported lifting element: {type(element).__name__}")
            name = element.id_short
            if not name or name in names:
                raise ValueError("Missing or duplicate sibling idShort")
            names.add(name)
            if isinstance(element, types.SubmodelElementCollection):
                check(element.value)

    check(submodel.submodel_elements)
    return submodel


class SemanticLiftingAdapter:
    """Register a trusted template and lift complete instance snapshots."""

    def __init__(self, domain: str, template_document: dict):
        from semantic.template_lifting import build_template_graph

        self.domain = domain
        template = _parse_submodel(template_document)
        self.template_id = template.id
        self._template_graph = build_template_graph(template, domain)

    def template_graph(self) -> Graph:
        return Graph() + self._template_graph

    def lift_instance(self, instance_document: dict) -> Graph:
        from semantic.instance_lifting import build_instance_graph

        instance = _parse_submodel(instance_document)
        if instance.id == self.template_id:
            raise ValueError("Instance and template identifiers must differ")
        if instance.submodel_elements is None:
            instance.submodel_elements = []
        return build_instance_graph(instance, self.domain, self.template_id)
