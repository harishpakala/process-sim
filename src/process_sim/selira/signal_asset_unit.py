"""Evidence-gated TEP signal -> instrument -> catalog product -> QUDT checks.

This module assesses a *proposed* mapping; it never infers installation or
authorizes a correspondence merely because units are convertible.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Mapping, Any

from process_sim.backends.tep.mapping import MEASUREMENT_NAMES, MEASUREMENT_UNITS
from process_sim.selira.unit_validation import (
    QUDT_QUANTITY_KIND, QUDT_UNIT, UnitAssessment, UnitStatus,
    convert_value, validate_units,
)


class CorrespondenceStatus(str, Enum):
    VALIDATED = "validated"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class SignalAssetUnitAssessment:
    status: CorrespondenceStatus
    signal: str
    instrument: str
    product: str
    unit_assessment: UnitAssessment
    reason: str

    @property
    def permits_asset_binding(self) -> bool:
        return self.status == CorrespondenceStatus.VALIDATED


def _property(elements: list[dict[str, Any]], name: str) -> str | None:
    return next((e.get("value") for e in elements if e.get("idShort") == name
                 and e.get("modelType") == "Property"), None)


def assess_xmeas7_pressure(
    catalog: Mapping[str, Any],
    *,
    inventory: Mapping[str, Any] | None = None,
    signal: str = "XMEAS7",
    instrument: str = "PI-1101",
    product: str = "EandH_PMP51B_Candidate",
    instrument_correspondence_verified: bool = False,
    product_configuration_verified: bool = False,
    installation_verified: bool = False,
) -> SignalAssetUnitAssessment:
    """Assess the reviewed reactor-pressure candidate, failing closed.

    When inventory is provided, verify the existing OperationalReference,\n    EquipmentTag and ProductReference join rather than inventing a mapping.\n    Boolean evidence flags must be supplied by an independent engineering
    verification process, never inferred from catalog metadata.
    """
    unknown = validate_units(None, None)
    if (signal, instrument, product) != (
        "XMEAS7", "PI-1101", "EandH_PMP51B_Candidate"
    ):
        return SignalAssetUnitAssessment(
            CorrespondenceStatus.UNRESOLVED, signal, instrument, product, unknown,
            "Only the reviewed XMEAS7 / PI-1101 / PMP51B candidate is supported",
        )
    if inventory is not None:
        assets = next(
            (x.get("value", []) for x in inventory.get("submodelElements", [])
             if x.get("idShort") == "Assets"), []
        )
        matches = [
            a for a in assets
            if _property(a.get("value", []), "OperationalReference") == signal
        ]
        if len(matches) != 1:
            return SignalAssetUnitAssessment(
                CorrespondenceStatus.UNRESOLVED, signal, instrument, product, unknown,
                "Inventory must contain exactly one matching operational signal",
            )
        fields = matches[0].get("value", [])
        catalog_reference = "https://example.org/product-types/" + product
        if (_property(fields, "EquipmentTag") != instrument
                or _property(fields, "ProductReference") != catalog_reference
                or _property(fields, "AssetType") != "LogicalMeasurement"):
            return SignalAssetUnitAssessment(
                CorrespondenceStatus.UNRESOLVED, signal, instrument, product, unknown,
                "Inventory instrument, product reference, or asset type disagrees",
            )
    if MEASUREMENT_NAMES.get(7) != "reactor_pressure" or MEASUREMENT_UNITS.get(7) != "kPa gauge":
        return SignalAssetUnitAssessment(
            CorrespondenceStatus.UNRESOLVED, signal, instrument, product, unknown,
            "TEP pressure source metadata is missing or has changed",
        )
    products = next(
        (x.get("value", []) for x in catalog.get("submodelElements", [])
         if x.get("idShort") == "Products"), []
    )
    entry = next((x for x in products if x.get("idShort") == product), None)
    if entry is None:
        return SignalAssetUnitAssessment(
            CorrespondenceStatus.UNRESOLVED, signal, instrument, product, unknown,
            "Product is absent from the catalog",
        )
    properties = entry.get("value", [])
    technical = next(
        (x.get("value", []) for x in properties if x.get("idShort") == "TechnicalProperties"), []
    )
    if (_property(technical, "PressureReference") != "Gauge"
            or _property(technical, "MeasurementRangeQUDTUnit") != QUDT_UNIT + "BAR"
            or _property(technical, "MeasurementRangeQUDTQuantityKind")
            != QUDT_QUANTITY_KIND + "Pressure"):
        return SignalAssetUnitAssessment(
            CorrespondenceStatus.UNRESOLVED, signal, instrument, product, unknown,
            "Product pressure unit, quantity kind, or gauge reference is not verified",
        )
    units = validate_units(
        QUDT_UNIT + "KiloPA", QUDT_UNIT + "BAR",
        expected_quantity_kind=QUDT_QUANTITY_KIND + "Pressure",
    )
    if units.status not in (UnitStatus.COMPATIBLE, UnitStatus.CONVERTIBLE):
        return SignalAssetUnitAssessment(
            CorrespondenceStatus.UNRESOLVED, signal, instrument, product, units,
            "Pressure units are not compatible",
        )
    if not all((instrument_correspondence_verified, product_configuration_verified,
                installation_verified)):
        return SignalAssetUnitAssessment(
            CorrespondenceStatus.AMBIGUOUS, signal, instrument, product, units,
            "Unit conversion is supported, but correspondence, configured product, "
            "and installation require independent verification",
        )
    return SignalAssetUnitAssessment(
        CorrespondenceStatus.VALIDATED, signal, instrument, product, units,
        "Gauge pressure unit conversion and all explicit engineering evidence verified",
    )


def convert_xmeas7_pressure(
    value_kpa_gauge: str | int | float | Decimal,
    assessment: SignalAssetUnitAssessment,
) -> Decimal:
    """Convert a TEP pressure only after the full correspondence is validated."""
    if not assessment.permits_asset_binding:
        raise ValueError("Unverified signal-to-asset correspondence")
    return convert_value(value_kpa_gauge, assessment.unit_assessment)
