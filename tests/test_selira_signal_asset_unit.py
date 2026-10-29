"""Evidence-gated TEP reactor pressure to catalog asset integration."""
from decimal import Decimal

import pytest

from process_sim.selira.signal_asset_unit import (
    CorrespondenceStatus, assess_xmeas7_pressure, convert_xmeas7_pressure,
)
from process_sim.selira.unit_validation import UnitStatus


@pytest.fixture
def catalog():
    def prop(name, value):
        return {"modelType": "Property", "idShort": name, "value": value}

    return {"submodelElements": [{
        "idShort": "Products",
        "value": [{
            "idShort": "EandH_PMP51B_Candidate",
            "value": [{
                "idShort": "TechnicalProperties",
                "value": [
                    prop("PressureReference", "Gauge"),
                    prop("MeasurementRangeQUDTUnit", "http://qudt.org/vocab/unit/BAR"),
                    prop("MeasurementRangeQUDTQuantityKind",
                         "http://qudt.org/vocab/quantitykind/Pressure"),
                ],
            }],
        }],
    }]}


def test_pressure_unit_conversion_does_not_authorize_binding(catalog):
    result = assess_xmeas7_pressure(catalog)
    assert result.status == CorrespondenceStatus.AMBIGUOUS
    assert result.unit_assessment.status == UnitStatus.CONVERTIBLE
    assert result.unit_assessment.multiplier == Decimal("0.01")
    assert not result.permits_asset_binding
    with pytest.raises(ValueError, match="Unverified"):
        convert_xmeas7_pressure("2700", result)


def test_explicit_engineering_evidence_enables_conversion(catalog):
    result = assess_xmeas7_pressure(
        catalog, instrument_correspondence_verified=True,
        product_configuration_verified=True, installation_verified=True,
    )
    assert result.status == CorrespondenceStatus.VALIDATED
    assert convert_xmeas7_pressure("2700", result) == Decimal("27.00")


@pytest.mark.parametrize("missing", [
    "instrument_correspondence_verified",
    "product_configuration_verified",
    "installation_verified",
])
def test_each_missing_evidence_fails_closed(catalog, missing):
    flags = dict(instrument_correspondence_verified=True,
                 product_configuration_verified=True, installation_verified=True)
    flags[missing] = False
    assert assess_xmeas7_pressure(catalog, **flags).status == CorrespondenceStatus.AMBIGUOUS


def test_absolute_pressure_cannot_substitute_for_gauge(catalog):
    props = catalog["submodelElements"][0]["value"][0]["value"][0]["value"]
    props[0]["value"] = "Absolute"
    assert assess_xmeas7_pressure(catalog).status == CorrespondenceStatus.UNRESOLVED


def test_unknown_product_and_signal_fail_closed(catalog):
    assert assess_xmeas7_pressure(catalog, product="Unknown").status == CorrespondenceStatus.UNRESOLVED
    assert assess_xmeas7_pressure(catalog, signal="XMEAS13").status == CorrespondenceStatus.UNRESOLVED


def test_missing_catalog_annotation_fails_closed(catalog):
    props = catalog["submodelElements"][0]["value"][0]["value"][0]["value"]
    props.pop()
    assert assess_xmeas7_pressure(catalog).status == CorrespondenceStatus.UNRESOLVED
