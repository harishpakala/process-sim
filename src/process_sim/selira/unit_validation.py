"""QUDT-based unit checks for SELiRA semantic information contracts.

Units must be supplied from trusted source metadata. This module never infers
an engineering signal's unit from its name or its physical quantity.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

QUDT_UNIT = "http://qudt.org/vocab/unit/"
QUDT_QUANTITY_KIND = "http://qudt.org/vocab/quantitykind/"


class UnitStatus(str, Enum):
    COMPATIBLE = "compatible"
    CONVERTIBLE = "convertible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class UnitDefinition:
    iri: str
    quantity_kind: str
    multiplier_to_si: Decimal


@dataclass(frozen=True)
class UnitAssessment:
    status: UnitStatus
    source_unit: str | None
    requested_unit: str | None
    quantity_kind: str | None
    multiplier: Decimal | None
    reason: str

    @property
    def permits_numerical_use(self) -> bool:
        return self.status in (UnitStatus.COMPATIBLE, UnitStatus.CONVERTIBLE)


# A deliberately small, reviewed QUDT subset. Extend using validated QUDT
# vocabulary data; do not silently guess unknown unit IRIs.
UNITS = {
    QUDT_UNIT + "PA": UnitDefinition(QUDT_UNIT + "PA", QUDT_QUANTITY_KIND + "Pressure", Decimal("1")),
    QUDT_UNIT + "KiloPA": UnitDefinition(QUDT_UNIT + "KiloPA", QUDT_QUANTITY_KIND + "Pressure", Decimal("1000")),
    QUDT_UNIT + "BAR": UnitDefinition(QUDT_UNIT + "BAR", QUDT_QUANTITY_KIND + "Pressure", Decimal("100000")),
    QUDT_UNIT + "KiloGM-PER-HR": UnitDefinition(QUDT_UNIT + "KiloGM-PER-HR", QUDT_QUANTITY_KIND + "MassFlowRate", Decimal("1") / Decimal("3600")),
    QUDT_UNIT + "M3-PER-HR": UnitDefinition(QUDT_UNIT + "M3-PER-HR", QUDT_QUANTITY_KIND + "VolumeFlowRate", Decimal("1") / Decimal("3600")),
    QUDT_UNIT + "K": UnitDefinition(QUDT_UNIT + "K", QUDT_QUANTITY_KIND + "ThermodynamicTemperature", Decimal("1")),
}


def validate_units(
    source_unit: str | None,
    requested_unit: str | None,
    *,
    expected_quantity_kind: str | None = None,
) -> UnitAssessment:
    """Check QUDT unit identity, quantity kind, and multiplicative conversion.

    An unknown or unregistered unit fails closed. No signal-to-unit assignment
    is created here. Temperature units requiring offsets are intentionally not
    included; only multiplicative conversions are supported.
    """
    if not source_unit or not requested_unit:
        return UnitAssessment(UnitStatus.UNKNOWN, source_unit, requested_unit, None, None,
                              "Source and requested QUDT units must both be known")
    source = UNITS.get(source_unit)
    target = UNITS.get(requested_unit)
    if source is None or target is None:
        return UnitAssessment(UnitStatus.UNKNOWN, source_unit, requested_unit, None, None,
                              "Unit not present in the validated QUDT unit registry")
    if source.quantity_kind != target.quantity_kind:
        return UnitAssessment(UnitStatus.INCOMPATIBLE, source_unit, requested_unit, None, None,
                              "QUDT quantity kinds differ")
    if expected_quantity_kind is not None and source.quantity_kind != expected_quantity_kind:
        return UnitAssessment(UnitStatus.INCOMPATIBLE, source_unit, requested_unit,
                              source.quantity_kind, None, "Unexpected quantity kind")
    multiplier = source.multiplier_to_si / target.multiplier_to_si
    status = UnitStatus.COMPATIBLE if source_unit == requested_unit else UnitStatus.CONVERTIBLE
    return UnitAssessment(status, source_unit, requested_unit, source.quantity_kind,
                          multiplier, "Unit identity confirmed" if status == UnitStatus.COMPATIBLE
                          else "Multiplicative QUDT conversion available")


def convert_value(value: str | int | float | Decimal, assessment: UnitAssessment) -> Decimal:
    """Convert a numeric value only after successful unit validation."""
    if not assessment.permits_numerical_use or assessment.multiplier is None:
        raise ValueError("Unit validation does not permit numerical use")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Invalid numeric observation") from exc
    if not number.is_finite():
        raise ValueError("Non-finite numeric observation")
    return number * assessment.multiplier
