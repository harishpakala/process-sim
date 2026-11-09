"""Controlled SELiRA comparison using an independent fixture oracle.

This is a deterministic synthetic benchmark, NOT live GraphDB validation.
The oracle is intentionally kept separate from the policies under test.
"""

# Created: 2026-10-29
# Author: Harish
from __future__ import annotations

from dataclasses import dataclass

from process_sim.backends.tep.mapping import MEASUREMENT_NAMES, MEASUREMENT_UNITS
from .resolution import extract_signal, resolve_correspondence
from .consumer_policy import authorize_use


@dataclass(frozen=True)
class Scenario:
    name: str
    property_name: str
    references: tuple[str, ...]
    declarations: tuple[dict, ...]
    expected_signal: str | None


def declaration(property_name, signal, *, status="validated", applicability="applicable"):
    return {
        "requestedProperty": property_name,
        "signal": signal,
        "reference": "opcua/" + signal,
        "validationStatus": status,
        "applicabilityStatus": applicability,
        "evidenceReferences": ["urn:synthetic:review:" + signal],
    }


def scenarios():
    """Fixture oracle uses TEP metadata, not the resolution implementation."""
    result = []
    for index in (7, 13, 16):
        prop = MEASUREMENT_NAMES[index]
        signal = f"XMEAS{index}"
        wrong = "XMEAS13" if index != 13 else "XMEAS7"
        assert MEASUREMENT_UNITS[index] == "kPa gauge"
        result.extend((
            Scenario(f"{signal}:correct", prop, ("opcua/" + signal,),
                     (declaration(prop, signal),), signal),
            Scenario(f"{signal}:wrong_unique", prop, ("opcua/" + wrong,),
                     (), None),
            Scenario(f"{signal}:no_review", prop, ("opcua/" + signal,),
                     (), None),
            Scenario(f"{signal}:competing", prop,
                     ("opcua/" + signal, "opcua/" + wrong),
                     (declaration(prop, signal),), None),
            Scenario(f"{signal}:rejected_competitor", prop,
                     ("opcua/" + signal, "opcua/" + wrong),
                     (declaration(prop, signal),
                      declaration(prop, wrong, status="rejected")), signal),
            Scenario(f"{signal}:inapplicable", prop, ("opcua/" + signal,),
                     (declaration(prop, signal, applicability="inapplicable"),), None),
        ))
    return tuple(result)


def legacy_select(references):
    """Existing asset-history policy: a unique recognized signal is 'mapped'."""
    signals = {signal for ref in references
               if (signal := extract_signal(ref)) is not None}
    return next(iter(signals)) if len(signals) == 1 else None


def evaluate(cases=None):
    """Return per-scenario outcomes and confusion counts for both policies.

    An accepted signal is correct only when it matches the fixture oracle.
    Withholding is correct only when the oracle has no authorized signal.
    """
    cases = scenarios() if cases is None else cases
    rows = []
    for case in cases:
        legacy = legacy_select(case.references)
        resolution = resolve_correspondence(
            case.property_name, list(case.references), case.declarations)
        selira = resolution.selected_signal if authorize_use(resolution) else None
        rows.append({
            "scenario": case.name,
            "oracle": case.expected_signal,
            "legacy": legacy,
            "selira": selira,
        })
    def metrics(key):
        return {
            "correct_accept": sum(r["oracle"] is not None and
                                  r[key] == r["oracle"] for r in rows),
            "unsafe_accept": sum(r[key] is not None and
                                 r[key] != r["oracle"] for r in rows),
            "correct_withhold": sum(r["oracle"] is None and
                                    r[key] is None for r in rows),
            "incorrect_withhold": sum(r["oracle"] is not None and
                                      r[key] is None for r in rows),
        }
    return {"scenarios": rows, "legacy": metrics("legacy"),
            "selira": metrics("selira")}
