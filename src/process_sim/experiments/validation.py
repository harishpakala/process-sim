"""Validation of recorded experiment events against declared ground truth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .models import GroundTruth


@dataclass(frozen=True)
class ValidationResult:
    """Deterministic validation result for one experiment run."""

    passed: bool
    checks: tuple[str, ...]
    failures: tuple[str, ...]


class ExperimentValidator:
    """Validate declared fault ground truth against canonical recorded events.

    Quantitative process-response validation is intentionally not performed yet.
    The first benchmark milestone establishes that the scheduled fault actually
    occurred at the declared target and simulation boundaries.
    """

    def validate_events(
        self,
        ground_truth: GroundTruth,
        events: Iterable[Any],
    ) -> ValidationResult:
        events = tuple(events)
        checks: list[str] = []
        failures: list[str] = []

        expected = ground_truth.fault
        fault_events = [
            event for event in events
            if getattr(event, "event_type", None) in {"FaultActivated", "FaultDeactivated"}
        ]

        if expected is None:
            checks.append("no expected fault declared")
            if fault_events:
                failures.append("recorded fault lifecycle events but ground truth declares no fault")
            return ValidationResult(not failures, tuple(checks), tuple(failures))

        activated = [event for event in fault_events if event.event_type == "FaultActivated"]
        deactivated = [event for event in fault_events if event.event_type == "FaultDeactivated"]

        matching_activation = [
            event for event in activated
            if event.subject == expected.target
            and event.metadata.get("fault_type") == expected.fault_type
        ]
        if not matching_activation:
            failures.append(
                f"missing activation for {expected.fault_type}:{expected.target}"
            )
        else:
            checks.append("fault activation target/type matched")
            activation_time = matching_activation[0].simulation_time_hours
            if abs(activation_time - expected.start_time_hours) > 1e-12:
                failures.append(
                    f"activation time {activation_time} != expected {expected.start_time_hours}"
                )
            else:
                checks.append("fault activation time matched")

        if expected.duration_hours is not None:
            expected_end = expected.start_time_hours + expected.duration_hours
            matching_deactivation = [
                event for event in deactivated
                if event.subject == expected.target
                and event.metadata.get("fault_type") == expected.fault_type
            ]
            if not matching_deactivation:
                failures.append(
                    f"missing deactivation for {expected.fault_type}:{expected.target}"
                )
            else:
                checks.append("fault deactivation target/type matched")
                deactivation_time = matching_deactivation[0].simulation_time_hours
                if abs(deactivation_time - expected_end) > 1e-12:
                    failures.append(
                        f"deactivation time {deactivation_time} != expected {expected_end}"
                    )
                else:
                    checks.append("fault deactivation time matched")

        return ValidationResult(not failures, tuple(checks), tuple(failures))
