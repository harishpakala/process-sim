"""Validation of recorded experiment events against declared ground truth."""

# Created: 2026-08-21
# Author: Harish

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from process_sim.recording import Event

from .models import GroundTruth


@dataclass(frozen=True)
class ValidationResult:
    """Result of validating recorded events against experiment ground truth."""

    passed: bool
    failures: tuple[str, ...] = field(default_factory=tuple)


class ExperimentValidator:
    """Validate deterministic fault lifecycle evidence for an experiment."""

    def validate_events(
        self, ground_truth: GroundTruth, events: Iterable[Event]
    ) -> ValidationResult:
        """Validate expected fault activation/deactivation events.

        The validator intentionally checks recorded lifecycle evidence rather than
        inferring process response from observations. This keeps ground-truth
        validation separate from response analysis and causal interpretation.
        """

        failures: list[str] = []
        event_list = list(events)
        expected = ground_truth.fault

        if expected is None:
            return ValidationResult(passed=True)

        activations = [
            event
            for event in event_list
            if event.event_type == "FaultActivated"
            and event.subject == expected.target
            and str(event.metadata.get("fault_type", "")) == expected.fault_type
        ]
        if not activations:
            failures.append(
                f"missing activation event for {expected.fault_type} {expected.target}"
            )
        else:
            activation = min(activations, key=lambda event: event.simulation_time_hours)
            if activation.simulation_time_hours != expected.start_time_hours:
                failures.append(
                    "activation time mismatch: "
                    f"expected {expected.start_time_hours}, "
                    f"got {activation.simulation_time_hours}"
                )

            if expected.duration_hours is not None:
                expected_end = expected.start_time_hours + expected.duration_hours
                deactivations = [
                    event
                    for event in event_list
                    if event.event_type == "FaultDeactivated"
                    and event.subject == expected.target
                    and str(event.metadata.get("fault_type", ""))
                    == expected.fault_type
                ]
                if not deactivations:
                    failures.append(
                        f"missing deactivation event for {expected.fault_type} "
                        f"{expected.target}"
                    )
                else:
                    deactivation = min(
                        deactivations, key=lambda event: event.simulation_time_hours
                    )
                    if deactivation.simulation_time_hours != expected_end:
                        failures.append(
                            "deactivation time mismatch: "
                            f"expected {expected_end}, "
                            f"got {deactivation.simulation_time_hours}"
                        )

        return ValidationResult(passed=not failures, failures=tuple(failures))
