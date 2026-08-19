"""Backend-independent simulator contract.

The core interface intentionally contains no TEP-specific names. Backend
adapters translate their native APIs into this contract.
"""

from typing import Protocol


class ProcessSimulator(Protocol):
    """Minimal contract for a process simulation backend."""

    def reset(self) -> None:
        """Return the simulator to its initial operating condition."""
        ...

    def step(self, n_steps: int = 1) -> bool:
        """Advance the simulation by one or more native integration steps."""
        ...

    def get_time_hours(self) -> float:
        """Return simulation time in hours."""
        ...

    def get_measurements(self):
        """Return the current process measurements."""
        ...

    def get_manipulated_variables(self):
        """Return the current manipulated variables."""
        ...

    def set_manipulated_variable(self, index: int, value: float) -> None:
        """Set a manipulated variable using a 1-based backend index."""
        ...
