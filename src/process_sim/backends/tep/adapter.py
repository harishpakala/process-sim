"""Thin adapter around the existing ProfBraatz ``tep`` package.

No TEP equations are implemented here. The adapter translates the existing
TEPSimulator API into the process-sim boundary and keeps TEP-specific details
out of the rest of the platform.
"""

from typing import Dict, Optional, Tuple

from .mapping import DISTURBANCE_NAMES


class TEPAdapter:
    """Adapter for ``tep.TEPSimulator``.

    Parameters
    ----------
    backend:
        ``"fortran"``, ``"python"`` or ``None`` for the ProfBraatz package's
        automatic backend selection.
    random_seed:
        Seed passed unchanged to the underlying simulator.
    """

    def __init__(self, backend: Optional[str] = None, random_seed: Optional[int] = None):
        try:
            from tep import TEPSimulator
        except ImportError as exc:
            raise ImportError(
                "TEPAdapter requires the ProfBraatz 'tep' package. "
                "Install it with 'pip install -e .' in the TEP repository."
            ) from exc

        kwargs = {"random_seed": random_seed}
        if backend is not None:
            kwargs["backend"] = backend

        self.simulator = TEPSimulator(**kwargs)

    @property
    def backend(self) -> str:
        """Return the backend selected by the ProfBraatz simulator."""
        return self.simulator.backend

    def reset(self) -> None:
        """Reset to the simulator's initialized steady-state condition."""
        self.simulator.initialize()

    def step(self, n_steps: int = 1) -> bool:
        """Advance by ``n_steps`` of the TEP simulator's native 1-second step."""
        if n_steps < 1:
            raise ValueError("n_steps must be >= 1")
        return self.simulator.step(n_steps=n_steps)

    def get_time_hours(self) -> float:
        """Return current simulation time in hours."""
        return float(self.simulator.time)

    def get_measurements(self):
        """Return the 41 current XMEAS values in reference ordering."""
        return self.simulator.get_measurements()

    def get_manipulated_variables(self):
        """Return the 12 current XMV values in reference ordering."""
        return self.simulator.get_manipulated_vars()

    def get_states(self):
        """Return the 50 current process states."""
        return self.simulator.get_states()

    def set_manipulated_variable(self, index: int, value: float) -> None:
        """Set XMV ``index`` using the ProfBraatz 1-based API."""
        if not 1 <= index <= 12:
            raise IndexError("XMV index must be in the range 1..12")
        self.simulator.set_mv(index, value)

    def set_disturbance(self, index: int, value: int = 1) -> None:
        """Set IDV ``index`` using the ProfBraatz 1-based API."""
        if not 1 <= index <= 20:
            raise IndexError("IDV index must be in the range 1..20")
        if value not in (0, 1):
            raise ValueError("disturbance value must be 0 or 1")
        self.simulator.set_disturbance(index, value)

    def clear_disturbances(self) -> None:
        """Disable all IDVs."""
        self.simulator.clear_disturbances()

    def get_disturbances(self):
        """Return the 20-element IDV vector."""
        return self.simulator.get_disturbances()

    def simulate(
        self,
        duration_hours: float,
        disturbances: Optional[Dict[int, Tuple[float, int]]] = None,
        record_interval: int = 1,
    ):
        """Run a batch simulation using the existing ProfBraatz API.

        ``disturbances`` uses the native TEP convention:
        ``{idv_index: (time_hours, value)}``.
        """
        return self.simulator.simulate(
            duration_hours=duration_hours,
            disturbances=disturbances,
            record_interval=record_interval,
        )

    def active_disturbances(self):
        """Return active 1-based IDV indices."""
        return self.simulator.get_active_disturbances()

    @staticmethod
    def disturbance_name(index: int) -> str:
        """Return a documented semantic name when one is available."""
        if not 1 <= index <= 20:
            raise IndexError("IDV index must be in the range 1..20")
        return DISTURBANCE_NAMES.get(index, f"idv_{index}_unknown")
