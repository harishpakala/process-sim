"""Independent finite-model reference semantics for the SAFSL SC-01 subset.

This module does not import the compiler, SPARQL, or pySHACL. It specifies
the contract's mathematical meaning for finite canonical entity sets.
"""

# Created: 2026-10-31
# Author: Harish
from dataclasses import dataclass
from typing import Mapping, FrozenSet


@dataclass(frozen=True)
class Scope:
    """Explicit applicability and authoritative evidence declarations."""
    applicable: FrozenSet[str]
    complete: bool = False
    identity_normalized: bool = False
    applicability_confirmed: bool = False


def matched_products(references, identifiers: Mapping[str, set]):
    """Return distinct canonical product keys, not matching value pairs."""
    return frozenset(
        product for product, values in identifiers.items()
        if any(str(ref) == str(value) for ref in references for value in values)
    )


def evaluate_sc01(
    assets: Mapping[str, set],
    products: Mapping[str, set],
    scope: Scope,
):
    """Finite semantics of forall asset: existsExactlyOne matching product.

    The two maps contain canonical entity IDs and their field values.
    Keys distinguish entities even if they share identifiers. Values are
    compared lexically, matching the TEP adapter's declared policy.

    Returns (verdict, per_asset_cardinality). An empty confirmed applicable
    population is NA; unconfirmed evidence is U, never V or F.
    """
    if not scope.applicability_confirmed:
        return "U", {}
    if not scope.complete or not scope.identity_normalized:
        return "U", {}
    if not scope.applicable:
        return "NA", {}
    if not scope.applicable.issubset(assets):
        return "U", {}
    cardinalities = {
        asset: len(matched_products(assets[asset], products))
        for asset in sorted(scope.applicable)
    }
    return ("V" if all(n == 1 for n in cardinalities.values()) else "F",
            cardinalities)
