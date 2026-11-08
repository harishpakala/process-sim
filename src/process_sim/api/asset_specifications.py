"""GraphDB-backed AAS asset -> product -> technical specification traceability.

No ECLASS identifier, unit, or engineering compatibility is inferred.
"""

# Created: 2026-10-19
# Author: Harish
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

AAS = "https://example.org/aas/"
INV = "https://example.org/assetinventory/"
CAT = "https://example.org/productcatalog/"

def asset_specifications(asset_id, endpoint):
    if not isinstance(asset_id, str) or not 1 <= len(asset_id) <= 512:
        raise ValueError("assetId is required (maximum 512 characters)")
    # Restrict to identifier characters; do not interpolate arbitrary SPARQL.
    if not re.fullmatch(r"[A-Za-z0-9_:/#.%+~\\-]+", asset_id):
        raise ValueError("Invalid assetId")
    query = f"""
PREFIX inv: <{INV}>
PREFIX cat: <{CAT}>
PREFIX aas: <{AAS}>
SELECT ?asset ?name ?tag ?productReference ?product ?manufacturer ?part
       ?spec ?specName ?specValue ?semanticId ?supplementalSemanticId
WHERE {{
  GRAPH ?assetGraph {{
    ?asset inv:hasAssetId ?assetId .
    FILTER(STR(?assetId) = {json.dumps(asset_id)})
    OPTIONAL {{ ?asset inv:hasAssetName ?name }}
    OPTIONAL {{ ?asset inv:hasEquipmentTag ?tag }}
    OPTIONAL {{ ?asset inv:hasProductReference ?productReference }}
  }}
  OPTIONAL {{
    GRAPH ?catalogGraph {{
      ?product cat:hasAssetIdentifier ?productIdentifier .
      FILTER(BOUND(?productReference) && STR(?productIdentifier) = STR(?productReference))
      OPTIONAL {{ ?product cat:hasManufacturerName ?manufacturer }}
      OPTIONAL {{ ?product cat:hasManufacturerPartNumber ?part }}
      OPTIONAL {{
        ?product cat:hasTechnicalProperties ?specCollection .
        ?specCollection aas:hasSubmodelElement ?spec .
        ?spec a aas:Property ;
              <http://www.w3.org/2000/01/rdf-schema#label> ?specName .
        OPTIONAL {{ ?spec aas:value ?specValue }}
        OPTIONAL {{ ?spec aas:semanticId ?semanticId }}
        OPTIONAL {{ ?spec aas:supplementalSemanticId ?supplementalSemanticId }}
      }}
    }}
  }}
}}
ORDER BY ?specName
LIMIT 1000
"""
    request = Request(endpoint, data=urlencode({"query": query}).encode("utf-8"),
                      headers={"Accept": "application/sparql-results+json",
                               "Content-Type": "application/x-www-form-urlencoded"},
                      method="POST")
    with urlopen(request, timeout=20) as response:
        payload = response.read(4_000_001)
    if len(payload) > 4_000_000:
        raise RuntimeError("GraphDB response exceeds 4 MB")
    bindings = json.loads(payload)["results"]["bindings"]
    if not bindings:
        raise LookupError("Asset not found in lifted Asset Inventory")
    def val(row, key):
        return row.get(key, {}).get("value")
    first = bindings[0]
    specs = {}
    for row in bindings:
        uri = val(row, "spec")
        if not uri:
            continue
        entry = specs.setdefault(uri, {"iri": uri, "name": val(row, "specName"),
                                       "value": val(row, "specValue"),
                                       "semanticIds": [], "supplementalSemanticIds": [],
                                       "verificationStatus": "unverified"})
        for key, dest in (("semanticId", "semanticIds"),
                          ("supplementalSemanticId", "supplementalSemanticIds")):
            value = val(row, key)
            if value and value not in entry[dest]:
                entry[dest].append(value)
    return {
        "assetId": asset_id, "assetIri": val(first, "asset"),
        "assetName": val(first, "name"), "equipmentTag": val(first, "tag"),
        "productReference": val(first, "productReference"),
        "product": ({"iri": val(first, "product"),
                     "manufacturer": val(first, "manufacturer"),
                     "partNumber": val(first, "part")} if val(first, "product") else None),
        "linkStatus": ("linked" if val(first, "product") else
                       "unresolved" if val(first, "productReference") else "not_specified"),
        "technicalSpecifications": list(specs.values()),
        "note": "Specifications are manufacturer/catalog claims, not verified installed operating limits. Units and ECLASS identifiers are not inferred.",
    }
