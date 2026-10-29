"""Computable correspondence checks against versioned project metadata.

Checks two separately maintained repository records: the DEXPI/ECAD scope
mapping and canonical TEP measurement metadata. This is not proof of physical
installation, live GraphDB consistency, or authenticity of source documents.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import re

from process_sim.backends.tep.mapping import MEASUREMENT_NAMES, MEASUREMENT_UNITS

# Project-assigned tags, transcribed from docs/semantic/TEP_DEXPI_ECAD_SCOPE.md.
# Keep explicit: these assertions must not be inferred from the candidate itself.
PRESSURE_TAGS = {
    "PI_101": ("XMEAS7", "reactor_pressure"),
    "PI_102": ("XMEAS13", "separator_pressure"),
    "PI_103": ("XMEAS16", "stripper_pressure"),
}
SOURCES = (
    "docs/semantic/TEP_DEXPI_ECAD_SCOPE.md",
    "src/process_sim/backends/tep/mapping.py",
)


@dataclass(frozen=True)
class EvidenceDecision:
    status: str
    asset_tag: str
    requested_property: str
    signal: str
    checks: dict[str, str]
    sources: tuple[str, ...]
    limitations: tuple[str, ...]

    def to_dict(self):
        return asdict(self)


def validate_pressure_correspondence(asset_tag, requested_property, signal,
                                     unit="kPa gauge", *, scope_version=None):
    """Compute status from curated project records, never caller review labels.

    Rejection requires a documented contradiction. Unsupported assets or
    unknown versions are unresolved rather than incorrectly rejected.
    """
    for value in (asset_tag, requested_property, signal, unit):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Nonempty string identifiers and unit required")
    if scope_version is not None and (not isinstance(scope_version, str)
                                      or not scope_version.strip()):
        raise ValueError("Invalid scope version")
    checks = {"identity": "unknown", "quantity": "unknown",
              "unit": "unknown", "version": "unknown",
              "applicability": "unknown", "provenance": "project_records"}
    limitations = (
        "Project scope mapping is curated, not independently authenticated.",
        "No live GraphDB, device identity, or physical installation check.",
        "No deployment configuration or temporal applicability verified.",
        "Source revision is not pinned to a verified immutable release.",
    )
    if scope_version is not None:
        return EvidenceDecision("unresolved", asset_tag, requested_property,
                                signal, checks, SOURCES, limitations)
    expected = PRESSURE_TAGS.get(asset_tag)
    if expected is None:
        return EvidenceDecision("unresolved", asset_tag, requested_property,
                                signal, checks, SOURCES, limitations)
    expected_signal, expected_property = expected
    checks["identity"] = "match" if signal == expected_signal else "contradiction"
    checks["quantity"] = ("match" if requested_property == expected_property
                          else "contradiction")
    match = re.fullmatch(r"XMEAS([1-9][0-9]*)", signal)
    index = int(match.group(1)) if match else None
    actual_name = MEASUREMENT_NAMES.get(index)
    actual_unit = MEASUREMENT_UNITS.get(index)
    if actual_name is not None and actual_name != requested_property:
        checks["quantity"] = "contradiction"
    if actual_unit is not None:
        checks["unit"] = "match" if actual_unit == unit else "contradiction"
    if "contradiction" in checks.values():
        status = "rejected"
    elif (checks["identity"] == "match" and checks["quantity"] == "match"
          and checks["unit"] == "match"):
        status = "supported_project_scope"
    else:
        status = "unresolved"
    return EvidenceDecision(status, asset_tag, requested_property,
                            signal, checks, SOURCES, limitations)
