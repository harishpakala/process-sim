"""Compile and evaluate SC-01 against the real semantic.instance_lifting RDF.

Read-only validation; completeness and canonical identity are caller attestations.
"""
from rdflib import Graph, Namespace
from pyshacl import validate

from .compiler import compile_contract
from .tep_nexus import real_contract_source
from .lifted_evidence import lift_sc01_instances

AI = Namespace("https://example.org/assetinventory/")
PC = Namespace("https://example.org/productcatalog/")


def compile_lifted_sc01(provenance):
    assets = provenance["assetinventory"]["template_id"]
    products = provenance["productcatalog"]["template_id"]
    return compile_contract(real_contract_source(), {"templates": {
        assets: {"class": str(AI.Asset), "fields": {"ProductReference": str(AI.hasProductReference)},
                 "target_by_predicate": True},
        products: {"class": str(PC.Product), "fields": {"AssetIdentifier": str(PC.hasAssetIdentifier)},
                   "match_by_predicate": True, "lexical_match": True},
    }})


def evaluate_lifted_sc01(*, graph=None, provenance=None,
                         evidence_complete=False, identity_normalized=False):
    """Return V/F/U/NA and SHACL report; never commit changes."""
    if graph is None or provenance is None:
        graph, provenance = lift_sc01_instances()
    ttl, manifest = compile_lifted_sc01(provenance)
    if not any(graph.subjects(AI.hasProductReference, None)):
        return {"verdict": "NA", "reason": "No assigned product references", "manifest": manifest}
    if not evidence_complete or not identity_normalized:
        return {"verdict": "U", "reason": "Completeness or canonical identity not attested",
                "manifest": manifest}
    try:
        conforms, _, report = validate(graph, shacl_graph=Graph().parse(data=ttl, format="turtle"),
                                       inference="none", advanced=False)
    except Exception as exc:
        return {"verdict": "U", "reason": f"SHACL execution error: {exc}", "manifest": manifest}
    return {"verdict": "V" if conforms else "F", "reason": "SC-01 conforms" if conforms else "SC-01 violated",
            "report": report, "manifest": manifest}


if __name__ == "__main__":
    result = evaluate_lifted_sc01()
    print(result["verdict"], result["reason"])
    print("Completeness and identity must be attested before a V/F decision.")
