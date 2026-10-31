"""SC-01 evidence from the repository's authoritative AAS instance lifting.

No alternate RDF mapping, GraphDB reads, or writes. This is a local
candidate-graph builder; authoritative source revision attestation is external.
"""
from __future__ import annotations

import json
from pathlib import Path

import aas_core3_1.jsonization as aas_jsonization
from rdflib import Graph, RDF
from semantic.ontoutils import compute_uri, build_path
from .compiler import SELIRA

from semantic.config import TARGETS
from semantic.instance_lifting import build_instance_graph
from semantic.template_lifting import build_template_graph
from .compiler import CompilationError


def lift_sc01_instances(*, targets=None, validate_structure=False):
    """Lift AssetInventory and ProductCatalog with their actual AAS template IDs.

    Returns (combined_graph, provenance). Structural SHACL is optional and
    runs locally against the existing authoritative template lifting.
    """
    selected = TARGETS if targets is None else targets
    wanted = {"assetinventory", "productcatalog"}
    chosen = {}
    for domain, template_path, instance_path in selected:
        if domain in wanted:
            if domain in chosen:
                raise CompilationError(f"Duplicate configured domain: {domain}")
            chosen[domain] = (Path(template_path), Path(instance_path))
    if set(chosen) != wanted:
        raise CompilationError(f"Missing SC-01 domains: {sorted(wanted - set(chosen))}")

    combined = Graph()
    provenance = {}
    for domain in sorted(wanted):
        template_path, instance_path = chosen[domain]
        template = aas_jsonization.submodel_from_jsonable(
            json.loads(template_path.read_text(encoding="utf-8")))
        instance = aas_jsonization.submodel_from_jsonable(
            json.loads(instance_path.read_text(encoding="utf-8")))
        graph = build_instance_graph(instance, domain, template.id)
        # Mark actual AAS Assets collection members, even without a reference.
        if domain == "assetinventory":
            asset_count = 0
            for container in instance.submodel_elements or ():
                if container.id_short != "Assets":
                    continue
                for asset in container.value or ():
                    from aas_core3_1.types import SubmodelElementCollection
                    if not isinstance(asset, SubmodelElementCollection):
                        continue
                    path = build_path(build_path("", container.id_short), asset.id_short)
                    graph.add((compute_uri(instance.id, path), RDF.type, SELIRA.SC01Asset))
                    asset_count += 1
            if asset_count == 0:
                raise CompilationError("AssetInventory has no asset members; focus population unconfirmed")
        if validate_structure:
            from pyshacl import validate
            conforms, _, report = validate(
                graph, shacl_graph=build_template_graph(template, domain),
                inference="none", advanced=True)
            if not conforms:
                raise CompilationError(f"{domain}: structural SHACL failed: {report}")
        combined += graph
        provenance[domain] = {
            "template_id": template.id,
            "instance_id": instance.id,
            "template_path": str(template_path),
            "instance_path": str(instance_path),
            "triple_count": len(graph),
            **({"asset_count": asset_count} if domain == "assetinventory" else {}),
        }
    return combined, provenance
