"""Fault scheduling and application primitives."""

# Created: 2026-08-19
# Author: Harish

from __future__ import annotations

from copy import deepcopy

from .models import Fault, FaultType


class FaultManager:
    """Own scheduled faults and apply supported signal-level mechanisms."""

    def __init__(self) -> None:
        self._faults: dict[str, Fault] = {}

    def add(self, fault: Fault) -> None:
        """Add or replace a fault by ID."""
        if fault.fault_id in self._faults:
            raise ValueError(f"fault already exists: {fault.fault_id}")
        if fault.start_time_hours < 0:
            raise ValueError("start_time_hours must be >= 0")
        if fault.duration_hours is not None and fault.duration_hours <= 0:
            raise ValueError("duration_hours must be > 0")
        self._faults[fault.fault_id] = fault

    def remove(self, fault_id: str) -> Fault:
        """Remove and return a fault."""
        try:
            return self._faults.pop(fault_id)
        except KeyError as exc:
            raise KeyError(f"unknown fault: {fault_id}") from exc

    def faults(self) -> tuple[Fault, ...]:
        """Return all configured faults in insertion order."""
        return tuple(self._faults.values())

    def active_faults(self, simulation_time_hours: float) -> tuple[Fault, ...]:
        """Return faults active at the supplied simulation time."""
        return tuple(
            fault for fault in self._faults.values()
            if fault.is_active(simulation_time_hours)
        )

    def apply(self, target: str, value: float, simulation_time_hours: float) -> float:
        """Apply active signal faults to one numeric target value.

        Bias and drift are signal transformations. Stuck faults replace the
        signal with their configured value. Process disturbances are kept as
        first-class faults but are not applied here because they belong inside
        the numerical process model.
        """
        result = float(value)
        for fault in self.active_faults(simulation_time_hours):
            if fault.target != target:
                continue
            if fault.fault_type is FaultType.BIAS:
                result += float(fault.magnitude or 0.0)
            elif fault.fault_type is FaultType.DRIFT:
                elapsed = simulation_time_hours - fault.start_time_hours
                result += float(fault.magnitude or 0.0) * elapsed
            elif fault.fault_type is FaultType.STUCK:
                if fault.value is None:
                    raise ValueError(f"stuck fault requires value: {fault.fault_id}")
                result = float(fault.value)
            elif fault.fault_type is FaultType.PROCESS_DISTURBANCE:
                continue
        return result

    def snapshot(self) -> tuple[Fault, ...]:
        """Return a detached snapshot suitable for persistence or inspection."""
        return tuple(deepcopy(fault) for fault in self._faults.values())
