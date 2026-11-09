"""Thin adapter around the existing ProfBraatz ``tep`` package.

No TEP equations are implemented here. The adapter translates the existing
TEPSimulator API into the process-sim boundary and keeps TEP-specific details
out of the rest of the platform.
"""

# Created: 2026-08-19
# Author: Harish

from typing import Callable, Dict, Optional, Tuple

import numpy as np

from process_sim.faults import FaultManager, FaultType

from .mapping import DISTURBANCE_NAMES


class _FaultAwareController:
    """Inject scheduled sensor faults into the native controller input path."""

    def __init__(self, controller, adapter: "TEPAdapter"):
        self._controller = controller
        self._adapter = adapter

    def calculate(self, xmeas, xmv, step):
        if self._adapter.fault_manager is None:
            faulted_xmeas = xmeas
        else:
            time_hours = self._adapter.get_time_hours()
            faulted_xmeas = [
                self._adapter.fault_manager.apply(
                    f"XMEAS{index}", value, time_hours
                )
                for index, value in enumerate(xmeas, start=1)
            ]
        return self._controller.calculate(faulted_xmeas, xmv, step)

    def reset(self):
        return self._controller.reset()


class TEPAdapter:
    """Adapter for ``tep.TEPSimulator``.

    Sensor faults are applied both to recorded observations and to the native
    closed-loop controller input path when the simulator is running in its
    native closed-loop mode. In OPC UA operational mode the adapter uses the
    TEP manual-control mode, so manipulated variables are owned by the
    external OPC UA client rather than by an in-process controller.

    Process-disturbance faults are translated to the native TEP IDV interface
    before each simulator step.
    """

    def __init__(
        self,
        backend: Optional[str] = None,
        random_seed: Optional[int] = None,
        control_mode: str = "closed_loop",
        fault_manager: Optional[FaultManager] = None,
        fault_event_sink: Optional[Callable[[dict], None]] = None,
    ):
        try:
            from tep import ControlMode, TEPSimulator
        except ImportError as exc:
            raise ImportError(
                "TEPAdapter requires the ProfBraatz 'tep' package. "
                "Install it with 'pip install -e .' in the TEP repository."
            ) from exc

        try:
            tep_control_mode = ControlMode(control_mode)
        except ValueError as exc:
            valid_modes = ", ".join(mode.value for mode in ControlMode)
            raise ValueError(
                f"control_mode must be one of: {valid_modes}"
            ) from exc

        kwargs = {
            "random_seed": random_seed,
            "control_mode": tep_control_mode,
        }
        if backend is not None:
            kwargs["backend"] = backend

        self.simulator = TEPSimulator(**kwargs)
        self._random_seed = random_seed
        self._control_mode = control_mode
        self.fault_manager = fault_manager
        self.fault_event_sink = fault_event_sink
        self._active_fault_ids: set[str] = set()
        self._fault_managed_idvs: set[int] = set()
        self._fault_previous_idvs: dict[int, int] = {}
        self._controller_delegate = None

    @property
    def backend(self) -> str:
        return self.simulator.backend

    @property
    def random_seed(self) -> Optional[int]:
        return self._random_seed

    @property
    def control_mode(self) -> str:
        """Return the TEP control mode used by this adapter."""
        return self._control_mode

    @property
    def external_control(self) -> bool:
        """Whether manipulated variables are intended to be externally owned."""
        return self._control_mode == "manual"

    def reset(self) -> None:
        self.simulator.initialize()
        self._controller_delegate = None
        self._active_fault_ids.clear()
        self._fault_managed_idvs.clear()
        self._fault_previous_idvs.clear()
        if not self.external_control:
            self._ensure_fault_aware_controller()

    def _ensure_fault_aware_controller(self) -> None:
        """Wrap the current native controller after simulator initialization."""
        if self.external_control:
            return
        controller = getattr(self.simulator, "controller", None)
        if controller is None or isinstance(controller, _FaultAwareController):
            return
        self._controller_delegate = controller
        self.simulator.controller = _FaultAwareController(controller, self)

    def step(self, n_steps: int = 1) -> bool:
        """Advance using native TEP steps with faults synchronized at boundaries."""
        if n_steps < 1:
            raise ValueError("n_steps must be >= 1")
        result = False
        for _ in range(n_steps):
            if not getattr(self.simulator, "initialized", False):
                self.simulator.initialize()
            if not self.external_control:
                self._ensure_fault_aware_controller()
            self.sync_faults()
            result = self.simulator.step(n_steps=1)
            self.sync_faults()
        return result

    def get_time_hours(self) -> float:
        return float(self.simulator.time)

    def get_measurements(self):
        measurements = np.asarray(self.simulator.get_measurements(), dtype=float)
        if self.fault_manager is None:
            return measurements
        time_hours = self.get_time_hours()
        return np.asarray(
            [
                self.fault_manager.apply(f"XMEAS{index}", value, time_hours)
                for index, value in enumerate(measurements, start=1)
            ],
            dtype=float,
        )

    def get_manipulated_variables(self):
        values = np.asarray(self.simulator.get_manipulated_vars(), dtype=float)
        if self.fault_manager is None:
            return values
        time_hours = self.get_time_hours()
        return np.asarray(
            [
                self.fault_manager.apply(f"XMV{index}", value, time_hours)
                for index, value in enumerate(values, start=1)
            ],
            dtype=float,
        )

    def get_states(self):
        return self.simulator.get_states()

    def set_manipulated_variable(self, index: int, value: float) -> None:
        if not 1 <= index <= 12:
            raise IndexError("XMV index must be in the range 1..12")
        self.simulator.set_mv(index, value)

    def set_disturbance(self, index: int, value: int = 1) -> None:
        if not 1 <= index <= 20:
            raise IndexError("IDV index must be in the range 1..20")
        if value not in (0, 1):
            raise ValueError("disturbance value must be 0 or 1")
        self.simulator.set_disturbance(index, value)

    def clear_disturbances(self) -> None:
        self.simulator.clear_disturbances()
        self._fault_managed_idvs.clear()
        self._fault_previous_idvs.clear()

    def get_disturbances(self):
        return self.simulator.get_disturbances()

    def configure_faults(
        self,
        fault_manager: FaultManager,
        fault_event_sink: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self.fault_manager = fault_manager
        if fault_event_sink is not None:
            self.fault_event_sink = fault_event_sink
        self._active_fault_ids.clear()
        self._fault_managed_idvs.clear()
        self._fault_previous_idvs.clear()
        if not self.external_control:
            self._ensure_fault_aware_controller()

    def sync_faults(self) -> None:
        """Apply scheduled process faults and emit lifecycle events at current time."""
        self._apply_process_disturbance_faults()
        self._publish_fault_lifecycle_events()

    def _process_disturbance_index(self, fault) -> int:
        """Resolve a fault target to a native 1-based TEP IDV index."""
        target = str(fault.target).strip().upper().replace("_", "")
        if target.startswith("IDV") and target[3:].isdigit():
            index = int(target[3:])
        else:
            index = int(fault.metadata.get("idv_index", 0))
        if not 1 <= index <= 20:
            raise ValueError(
                f"process disturbance fault {fault.fault_id!r} must identify IDV1..IDV20"
            )
        return index

    def _apply_process_disturbance_faults(self) -> None:
        """Translate active process faults into the native TEP IDV vector."""
        if self.fault_manager is None:
            return

        active_faults = [
            fault
            for fault in self.fault_manager.active_faults(self.get_time_hours())
            if fault.fault_type is FaultType.PROCESS_DISTURBANCE
        ]
        active_idvs = {self._process_disturbance_index(fault) for fault in active_faults}

        for index in sorted(active_idvs - self._fault_managed_idvs):
            self._fault_previous_idvs[index] = int(self.get_disturbances()[index - 1])

        for index in sorted(self._fault_managed_idvs - active_idvs):
            self.simulator.set_disturbance(index, self._fault_previous_idvs.pop(index, 0))

        for index in sorted(active_idvs):
            self.simulator.set_disturbance(index, 1)

        self._fault_managed_idvs = active_idvs

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
        """Run the native ProfBraatz batch simulation."""
        return self.simulator.simulate(
            duration_hours=duration_hours,
            disturbances=disturbances,
            record_interval=record_interval,
        )

    def active_disturbances(self):
        return self.simulator.get_active_disturbances()

    @staticmethod
    def disturbance_name(index: int) -> str:
        if not 1 <= index <= 20:
            raise IndexError("IDV index must be in the range 1..20")
        return DISTURBANCE_NAMES.get(index, f"idv_{index}_unknown")
