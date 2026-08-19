"""Thin adapter around the existing ProfBraatz ``tep`` package.

No TEP equations are implemented here. The adapter translates the existing
TEPSimulator API into the process-sim boundary and keeps TEP-specific details
out of the rest of the platform.
"""

from typing import Callable, Dict, Optional, Tuple

from process_sim.faults import FaultManager, FaultType

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
    fault_manager:
        Optional fault manager used to transform published XMEAS/XMV values.
    fault_event_sink:
        Optional callback receiving fault lifecycle event dictionaries.
    """

    def __init__(
        self,
        backend: Optional[str] = None,
        random_seed: Optional[int] = None,
        fault_manager: Optional[FaultManager] = None,
        fault_event_sink: Optional[Callable[[dict], None]] = None,
    ):
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
        self.fault_manager = fault_manager
        self.fault_event_sink = fault_event_sink
        self._active_fault_ids: set[str] = set()

    @property
    def backend(self) -> str:
        """Return the backend selected by the ProfBraatz simulator."""
        return self.simulator.backend

    def reset(self) -> None:
        """Reset to the simulator's initialized steady-state condition."""
        self.simulator.initialize()
        self._active_fault_ids.clear()

    def step(self, n_steps: int = 1) -> bool:
        """Advance by ``n_steps`` of the TEP simulator's native 1-second step."""
        if n_steps < 1:
            raise ValueError("n_steps must be >= 1")
        result = self.simulator.step(n_steps=n_steps)
        self._publish_fault_lifecycle_events()
        return result

    def get_time_hours(self) -> float:
        """Return current simulation time in hours."""
        return float(self.simulator.time)

    def get_measurements(self):
        """Return the 41 current XMEAS values, including active sensor faults."""
        measurements = list(self.simulator.get_measurements())
        if self.fault_manager is None:
            return measurements
        time_hours = self.get_time_hours()
        return [
            self.fault_manager.apply(f"XMEAS{index}", value, time_hours)
            for index, value in enumerate(measurements, start=1)
        ]

    def get_manipulated_variables(self):
        """Return the 12 current XMV values, including active actuator faults."""
        values = list(self.simulator.get_manipulated_vars())
        if self.fault_manager is None:
            return values
        time_hours = self.get_time_hours()
        return [
            self.fault_manager.apply(f"XMV{index}", value, time_hours)
            for index, value in enumerate(values, start=1)
        ]

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

    def configure_faults(
        self,
        fault_manager: FaultManager,
        fault_event_sink: Optional[Callable[[dict], None]] = None,
    ) -> None:
        """Attach a fault manager and optional lifecycle-event callback."""
        self.fault_manager = fault_manager
        if fault_event_sink is not None:
            self.fault_event_sink = fault_event_sink
        self._active_fault_ids.clear()

    def _publish_fault_lifecycle_events(self) -> None:
        if self.fault_manager is None or self.fault_event_sink is None:
            return
        active = {
            fault.fault_id: fault
            for fault in self.fault_manager.active_faults(self.get_time_hours())
        }
        current_ids = set(active)
        for fault_id in sorted(current_ids - self._active_fault_ids):
            fault = active[fault_id]
            self.fault_event_sink(self._fault_event("FaultActivated", fault))
        for fault_id in sorted(self._active_fault_ids - current_ids):
            fault = next(
                (item for item in self.fault_manager.faults() if item.fault_id == fault_id),
                None,
            )
            if fault is not None:
                self.fault_event_sink(self._fault_event("FaultDeactivated", fault))
        self._active_fault_ids = current_ids

    def _fault_event(self, event_type: str, fault) -> dict:
        return {
            "event_type": event_type,
            "fault_id": fault.fault_id,
            "fault_type": fault.fault_type.value,
            "target": fault.target,
            "simulation_time_hours": self.get_time_hours(),
            "metadata": dict(fault.metadata),
        }

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
