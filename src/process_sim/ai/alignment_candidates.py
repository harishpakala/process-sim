"""Reviewed candidates for cross-domain catalog-property / operational-signal alignment.

This is a review queue, not a verified ECLASS property dictionary. Product
classification IRDIs must never be substituted for characteristic IRDIs.
"""
from __future__ import annotations

CANDIDATES = (
    ("TEP_XMEAS7", "XMEAS7", "SMC_PSE550", "RatedDifferentialPressure", "pressure"),
    ("TEP_XMEAS7", "XMEAS7", "SMC_PSE550", "OperatingPressure", "pressure"),
    ("TEP_XMEAS7", "XMEAS7", "SMC_PSE550", "ProofPressure", "pressure"),
    ("TEP_XMEAS8", "XMEAS8", "IFM_LW2720", "MeasuringRange", "level"),
    ("TEP_XMEAS1", "XMEAS1", "SMC_PFMV505_1", "RatedFlowRange", "flow"),
)

def alignment_review_queue():
    """Return proposed cases with explicit missing evidence and no IRDI invention."""
    return [{
        "assetId": asset, "signal": signal, "productCatalogEntry": product,
        "catalogProperty": prop, "candidateMeasuredQuantity": quantity,
        "verificationStatus": "proposed",
        "propertyTermIrdi": None, "measuredQuantityTermIrdi": None,
        "evidenceRequired": [
            "Authoritative characteristic IRDI, if available",
            "Verified operational quantity and engineering measurement basis",
            "Unit and conversion evidence",
            "Specification applicability and interpretation",
            "Reviewed asset/product/signal relationship",
        ],
        "comparisonAuthorized": False,
    } for asset, signal, product, prop, quantity in CANDIDATES]
