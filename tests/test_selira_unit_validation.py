"""Unit contract checks: no invented signal units or implicit authorization."""
from decimal import Decimal

import pytest

from process_sim.selira.unit_validation import (
    QUDT_QUANTITY_KIND, QUDT_UNIT, UnitStatus, convert_value, validate_units,
)


def test_missing_signal_unit_is_unknown_and_withheld():
    result = validate_units(None, QUDT_UNIT + "BAR")
    assert result.status == UnitStatus.UNKNOWN
    assert not result.permits_numerical_use
    with pytest.raises(ValueError):
        convert_value("1", result)


def test_same_qudt_unit():
    result = validate_units(QUDT_UNIT + "BAR", QUDT_UNIT + "BAR",
                            expected_quantity_kind=QUDT_QUANTITY_KIND + "Pressure")
    assert result.status == UnitStatus.COMPATIBLE
    assert convert_value("2.5", result) == Decimal("2.5")


def test_pressure_conversion():
    result = validate_units(QUDT_UNIT + "KiloPA", QUDT_UNIT + "BAR",
                            expected_quantity_kind=QUDT_QUANTITY_KIND + "Pressure")
    assert result.status == UnitStatus.CONVERTIBLE
    assert convert_value("1000", result) == Decimal("10")


def test_incompatible_quantities_withheld():
    result = validate_units(QUDT_UNIT + "BAR", QUDT_UNIT + "K")
    assert result.status == UnitStatus.INCOMPATIBLE
    assert not result.permits_numerical_use


def test_expected_quantity_kind_checked():
    result = validate_units(QUDT_UNIT + "BAR", QUDT_UNIT + "BAR",
                            expected_quantity_kind=QUDT_QUANTITY_KIND + "ThermodynamicTemperature")
    assert result.status == UnitStatus.INCOMPATIBLE


def test_unknown_qudt_unit_withheld():
    result = validate_units(QUDT_UNIT + "MadeUpUnit", QUDT_UNIT + "BAR")
    assert result.status == UnitStatus.UNKNOWN


def test_no_unverified_temperature_offset_conversion():
    result = validate_units(QUDT_UNIT + "DEG_C", QUDT_UNIT + "K")
    assert result.status == UnitStatus.UNKNOWN


def test_nonfinite_values_rejected():
    result = validate_units(QUDT_UNIT + "PA", QUDT_UNIT + "PA")
    with pytest.raises(ValueError):
        convert_value("NaN", result)


def test_flow_mass_unit_identity():
    result = validate_units(QUDT_UNIT + "KiloGM-PER-HR", QUDT_UNIT + "KiloGM-PER-HR",
                            expected_quantity_kind=QUDT_QUANTITY_KIND + "MassFlowRate")
    assert result.status == UnitStatus.COMPATIBLE
    assert convert_value("3750", result) == Decimal("3750")


def test_flow_volume_unit_identity():
    result = validate_units(QUDT_UNIT + "M3-PER-HR", QUDT_UNIT + "M3-PER-HR",
                            expected_quantity_kind=QUDT_QUANTITY_KIND + "VolumeFlowRate")
    assert result.status == UnitStatus.COMPATIBLE


def test_mass_to_volume_flow_fails_closed_without_density():
    result = validate_units(QUDT_UNIT + "KiloGM-PER-HR", QUDT_UNIT + "M3-PER-HR")
    assert result.status == UnitStatus.INCOMPATIBLE
    with pytest.raises(ValueError):
        convert_value("100", result)
