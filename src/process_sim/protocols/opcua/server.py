"""OPC UA server adapter for a process-sim simulator."""

from __future__ import annotations

import asyncio
import json
from typing import Callable

from process_sim.faults import Fault, FaultManager, FaultType


class OPCUAServer:
    """Expose a process simulator through an OPC UA server.

    The server owns the OPC UA contract only. Fault semantics remain in
    :class:`FaultManager` and are applied by the simulator adapter.
    """

    def __init__(
        self,
        simulator,
        endpoint="opc.tcp://0.0.0.0:4841/process-sim/",
        namespace_uri="urn:process-sim:opcua",
        real_time_factor=1.0,
        update_interval_seconds=1.0,
        event_callback: Callable[[int, float, float], None] | None = None,
        fault_manager: FaultManager | None = None,
        fault_event_callback: Callable[[dict], None] | None = None,
    ):
        if real_time_factor <= 0:
            raise ValueError("real_time_factor must be > 0")
        if update_interval_seconds <= 0:
            raise ValueError("update_interval_seconds must be > 0")

        self.simulator = simulator
        self.endpoint = endpoint
        self.namespace_uri = namespace_uri
        self.event_callback = event_callback
        self.fault_manager = fault_manager or FaultManager()
        self.fault_event_callback = fault_event_callback
        self._server = None
        self._namespace_index = None
        self._time_node = None
        self._running_node = None
        self._real_time_factor_node = None
        self._fault_count_node = None
        self._measurement_nodes = []
        self._mv_nodes = []
        self._simulation_task = None
        self._real_time_factor = float(real_time_factor)
        self._update_interval_seconds = float(update_interval_seconds)
        self._last_synced_mvs = []

        configure_faults = getattr(self.simulator, "configure_faults", None)
        if callable(configure_faults):
            configure_faults(self.fault_manager, self._handle_fault_event)

    async def start(self):
        from asyncua import Server, ua

        self._server = Server()
        await self._server.init()
        self._server.set_endpoint(self.endpoint)
        self._namespace_index = await self._server.register_namespace(self.namespace_uri)
        tep = await self._server.nodes.objects.add_object(self._namespace_index, "TEP")
        simulation = await tep.add_object(self._namespace_index, "Simulation")
        self._time_node = await simulation.add_variable(
            self._namespace_index, "TimeHours", float(self.simulator.get_time_hours())
        )
        self._running_node = await simulation.add_variable(
            self._namespace_index, "Running", False
        )
        self._real_time_factor_node = await simulation.add_variable(
            self._namespace_index, "RealTimeFactor", self._real_time_factor
        )
        await self._time_node.set_read_only()
        await self._running_node.set_read_only()
        await self._real_time_factor_node.set_writable()
        await simulation.add_method(self._namespace_index, "Start", self._start_method)
        await simulation.add_method(self._namespace_index, "Stop", self._stop_method)
        await simulation.add_method(self._namespace_index, "Reset", self._reset_method)

        fault_management = await tep.add_object(
            self._namespace_index, "FaultManagement"
        )
        self._fault_count_node = await fault_management.add_variable(
            self._namespace_index, "FaultCount", len(self.fault_manager.faults())
        )
        await self._fault_count_node.set_read_only()
        await fault_management.add_method(
            self._namespace_index,
            "InjectFault",
            self._inject_fault_method,
            [
                ua.VariantType.String,
                ua.VariantType.String,
                ua.VariantType.String,
                ua.VariantType.Double,
                ua.VariantType.Double,
                ua.VariantType.Double,
            ],
            [ua.VariantType.Boolean],
        )
        await fault_management.add_method(
            self._namespace_index,
            "ClearFault",
            self._clear_fault_method,
            [ua.VariantType.String],
            [ua.VariantType.Boolean],
        )
        await fault_management.add_method(
            self._namespace_index,
            "ClearAllFaults",
            self._clear_all_faults_method,
            [],
            [ua.VariantType.Boolean],
        )
        await fault_management.add_method(
            self._namespace_index,
            "ListFaults",
            self._list_faults_method,
            [],
            [ua.VariantType.String],
        )

        measurements = await tep.add_object(self._namespace_index, "Measurements")
        self._measurement_nodes = []
        for index, value in enumerate(self.simulator.get_measurements(), start=1):
            node = await measurements.add_variable(
                self._namespace_index, f"XMEAS{index}", float(value)
            )
            await node.set_read_only()
            self._measurement_nodes.append(node)

        mvs = await tep.add_object(self._namespace_index, "ManipulatedVariables")
        self._mv_nodes = []
        for index, value in enumerate(
            self.simulator.get_manipulated_variables(), start=1
        ):
            node = await mvs.add_variable(
                self._namespace_index, f"XMV{index}", float(value)
            )
            await node.set_writable()
            self._mv_nodes.append(node)
        self._last_synced_mvs = [
            float(value) for value in self.simulator.get_manipulated_variables()
        ]

        await self._server.start()
        await self.update(False)

    @staticmethod
    def _unwrap_method_argument(value):
        """Return the Python value from an asyncua Variant argument.

        asyncua passes OPC UA method inputs to server callbacks as ``ua.Variant``
        objects. Internal/direct calls may still pass ordinary Python values, so
        both forms are accepted.
        """
        return getattr(value, "Value", value)

    async def _start_method(self, parent):
        await self.start_simulation()
        return True

    async def _stop_method(self, parent):
        await self.stop_simulation()
        return True

    async def _reset_method(self, parent):
        await self.reset_simulation()
        return True

    async def _inject_fault_method(
        self, parent, fault_id, fault_type, target, magnitude, value, duration_hours
    ):
        return self.inject_fault(
            str(self._unwrap_method_argument(fault_id)),
            str(self._unwrap_method_argument(fault_type)),
            str(self._unwrap_method_argument(target)),
            float(self._unwrap_method_argument(magnitude)),
            float(self._unwrap_method_argument(value)),
            float(self._unwrap_method_argument(duration_hours)),
        )

    async def _clear_fault_method(self, parent, fault_id):
        return self.clear_fault(str(self._unwrap_method_argument(fault_id)))

    async def _clear_all_faults_method(self, parent):
        return self.clear_all_faults()

    async def _list_faults_method(self, parent):
        return self.list_faults()

    def inject_fault(
        self,
        fault_id: str,
        fault_type: str,
        target: str,
        magnitude: float = 0.0,
        value: float = 0.0,
        duration_hours: float = 0.0,
    ) -> bool:
        """Inject an operator fault at the current simulation boundary.

        ``duration_hours == 0`` means the fault remains active until explicitly
        cleared. A positive duration schedules deactivation from the current
        simulation time. ``value`` is used by stuck faults; ``magnitude`` is
        used by bias, drift, and process-disturbance faults.
        """
        fault_kind = FaultType(str(fault_type).strip().lower())
        if not fault_id.strip():
            raise ValueError("fault_id must not be empty")
        if not target.strip():
            raise ValueError("target must not be empty")
        if duration_hours < 0:
            raise ValueError("duration_hours must be >= 0")

        start = float(self.simulator.get_time_hours())
        duration = None if duration_hours == 0 else float(duration_hours)
        metadata = {"injection_source": "opcua", "operator_injected": True}
        if fault_kind is FaultType.PROCESS_DISTURBANCE:
            metadata["idv_index"] = self._resolve_idv_index(target)

        fault = Fault(
            fault_id=fault_id.strip(),
            fault_type=fault_kind,
            target=target.strip(),
            magnitude=float(magnitude),
            value=float(value) if fault_kind is FaultType.STUCK else None,
            start_time_hours=start,
            duration_hours=duration,
            metadata=metadata,
        )
        self.fault_manager.add(fault)
        self._refresh_fault_count()
        self._emit_operator_fault_event("FaultInjected", fault)
        return True

    def clear_fault(self, fault_id: str) -> bool:
        """Clear an operator fault immediately and emit provenance metadata."""
        fault = self.fault_manager.remove(fault_id)
        self._refresh_fault_count()
        self._emit_operator_fault_event("FaultCleared", fault)
        sync_faults = getattr(self.simulator, "sync_faults", None)
        if callable(sync_faults):
            sync_faults()
        return True

    def clear_all_faults(self) -> bool:
        """Clear all configured operator faults."""
        for fault_id in [fault.fault_id for fault in self.fault_manager.faults()]:
            self.clear_fault(fault_id)
        return True

    def list_faults(self) -> str:
        """Return the configured fault set as a stable JSON string."""
        faults = []
        for fault in self.fault_manager.faults():
            faults.append(
                {
                    "fault_id": fault.fault_id,
                    "fault_type": fault.fault_type.value,
                    "target": fault.target,
                    "magnitude": fault.magnitude,
                    "value": fault.value,
                    "start_time_hours": fault.start_time_hours,
                    "duration_hours": fault.duration_hours,
                    "metadata": dict(fault.metadata),
                }
            )
        return json.dumps(faults, sort_keys=True)

    def _resolve_idv_index(self, target: str) -> int:
        normalized = target.strip().upper().replace("_", "")
        if not normalized.startswith("IDV"):
            raise ValueError("process_disturbance target must be IDV1..IDV20")
        try:
            index = int(normalized[3:])
        except ValueError as exc:
            raise ValueError("process_disturbance target must be IDV1..IDV20") from exc
        if not 1 <= index <= 20:
            raise ValueError("process_disturbance target must be IDV1..IDV20")
        return index

    def _refresh_fault_count(self):
        if self._fault_count_node is None:
            return
        count = len(self.fault_manager.faults())
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._fault_count_node.write_value(count))

    def _emit_operator_fault_event(self, event_type: str, fault: Fault):
        if self.fault_event_callback is None:
            return
        self.fault_event_callback(
            {
                "event_type": event_type,
                "fault_id": fault.fault_id,
                "fault_type": fault.fault_type.value,
                "target": fault.target,
                "simulation_time_hours": self.simulator.get_time_hours(),
                "metadata": dict(fault.metadata),
            }
        )

    def _handle_fault_event(self, event):
        if self.fault_event_callback is not None:
            self.fault_event_callback(event)

    async def sync_manipulated_variables(self):
        """Apply operator-written XMV values to the simulator."""
        if not self._mv_nodes:
            return
        for index, node in enumerate(self._mv_nodes, start=1):
            value = float(await node.read_value())
            previous = self._last_synced_mvs[index - 1]
            if value == previous:
                continue
            self.simulator.set_manipulated_variable(index, value)
            self._last_synced_mvs[index - 1] = value
            if self.event_callback is not None:
                self.event_callback(index, previous, value)

    async def update(self, running: bool):
        """Publish simulator state to OPC UA nodes."""
        if self._time_node is not None:
            await self._time_node.write_value(float(self.simulator.get_time_hours()))
        if self._running_node is not None:
            await self._running_node.write_value(bool(running))
        if self._real_time_factor_node is not None:
            await self._real_time_factor_node.write_value(self._real_time_factor)
        if self._measurement_nodes:
            measurements = self.simulator.get_measurements()
            for node, value in zip(self._measurement_nodes, measurements):
                await node.write_value(float(value))
        if self._mv_nodes:
            measurements = self.simulator.get_manipulated_variables()
            for node, value in zip(self._mv_nodes, measurements):
                await node.write_value(float(value))

    async def start_simulation(self):
        if self._simulation_task is not None and not self._simulation_task.done():
            return
        self._simulation_task = asyncio.create_task(self._simulation_loop())

    async def stop_simulation(self):
        task = self._simulation_task
        if task is None:
            return
        self._simulation_task = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await self.update(False)

    async def reset_simulation(self):
        await self.stop_simulation()
        self.simulator.reset()
        configure_faults = getattr(self.simulator, "configure_faults", None)
        if callable(configure_faults):
            configure_faults(self.fault_manager, self._handle_fault_event)
        self._last_synced_mvs = [
            float(value) for value in self.simulator.get_manipulated_variables()
        ]
        await self.update(False)

    async def _simulation_loop(self):
        while True:
            await asyncio.sleep(self._update_interval_seconds)
            steps = max(1, int(round(self._update_interval_seconds * self._real_time_factor)))
            for _ in range(steps):
                self.simulator.step()
            await self.sync_manipulated_variables()
            await self.update(True)

    async def run(self):
        await self.start()
        await self.start_simulation()
        try:
            while True:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop_simulation()
            await self._server.stop()
