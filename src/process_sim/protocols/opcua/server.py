"""OPC UA server adapter for a process-sim simulator."""

from __future__ import annotations

import asyncio
import json
from typing import Callable

from asyncua import ua

from process_sim.faults import Fault, FaultManager, FaultType


class OPCUAServer:
    """Expose a process simulator through an OPC UA server.

    The server owns the OPC UA contract only. Fault semantics remain in
    :class:`FaultManager` and are applied by the simulator adapter.

    For operational use, manipulated variables are externally owned: the
    simulator runs in manual-control mode and OPC UA clients provide the
    control actions by writing the XMV nodes. The native TEP closed-loop
    controller remains available to non-OPC-UA benchmark paths as a reference
    controller.
    """

    def __init__(self, simulator, endpoint="opc.tcp://0.0.0.0:4841/process-sim/", namespace_uri="urn:process-sim:opcua", real_time_factor=1.0, update_interval_seconds=1.0, event_callback: Callable[[int, float, float], None] | None = None, fault_manager: FaultManager | None = None, fault_event_callback: Callable[[dict], None] | None = None):
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
        self._control_mode_node = None
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

    def _control_mode_name(self) -> str:
        if getattr(self.simulator, "external_control", False):
            return "external_opcua"
        return "native"

    async def start(self):
        from asyncua import Server
        self._server = Server()
        await self._server.init()
        self._server.set_endpoint(self.endpoint)
        self._namespace_index = await self._server.register_namespace(self.namespace_uri)
        tep = await self._server.nodes.objects.add_object(self._namespace_index, "TEP")
        simulation = await tep.add_object(self._namespace_index, "Simulation")
        self._time_node = await simulation.add_variable(self._namespace_index, "TimeHours", float(self.simulator.get_time_hours()))
        self._running_node = await simulation.add_variable(self._namespace_index, "Running", False)
        self._control_mode_node = await simulation.add_variable(self._namespace_index, "ControlMode", self._control_mode_name())
        self._real_time_factor_node = await simulation.add_variable(self._namespace_index, "RealTimeFactor", self._real_time_factor)
        await self._time_node.set_read_only()
        await self._running_node.set_read_only()
        await self._control_mode_node.set_read_only()
        await self._real_time_factor_node.set_writable()
        await simulation.add_method(self._namespace_index, "Start", self._start_method, [], [ua.VariantType.Boolean])
        await simulation.add_method(self._namespace_index, "Stop", self._stop_method, [], [ua.VariantType.Boolean])
        await simulation.add_method(self._namespace_index, "Reset", self._reset_method, [], [ua.VariantType.Boolean])
        fault_management = await tep.add_object(self._namespace_index, "FaultManagement")
        self._fault_count_node = await fault_management.add_variable(self._namespace_index, "FaultCount", len(self.fault_manager.faults()))
        await self._fault_count_node.set_read_only()
        await fault_management.add_method(self._namespace_index, "InjectFault", self._inject_fault_method, [ua.VariantType.String, ua.VariantType.String, ua.VariantType.String, ua.VariantType.Double, ua.VariantType.Double, ua.VariantType.Double], [ua.VariantType.Boolean])
        await fault_management.add_method(self._namespace_index, "ClearFault", self._clear_fault_method, [ua.VariantType.String], [ua.VariantType.Boolean])
        await fault_management.add_method(self._namespace_index, "ClearAllFaults", self._clear_all_faults_method, [], [ua.VariantType.Boolean])
        await fault_management.add_method(self._namespace_index, "ListFaults", self._list_faults_method, [], [ua.VariantType.String])
        measurements = await tep.add_object(self._namespace_index, "Measurements")
        self._measurement_nodes = []
        for index, value in enumerate(self.simulator.get_measurements(), start=1):
            node = await measurements.add_variable(ua.NodeId(f"TEP.Measurements.XMEAS{index}", self._namespace_index), f"XMEAS{index}", float(value))
            await node.set_read_only()
            self._measurement_nodes.append(node)
        mvs = await tep.add_object(self._namespace_index, "ManipulatedVariables")
        self._mv_nodes = []
        for index, value in enumerate(self.simulator.get_manipulated_variables(), start=1):
            node = await mvs.add_variable(ua.NodeId(f"TEP.ManipulatedVariables.XMV{index}", self._namespace_index), f"XMV{index}", float(value))
            await node.set_writable()
            self._mv_nodes.append(node)
        self._last_synced_mvs = [float(value) for value in self.simulator.get_manipulated_variables()]
        await self._server.start()
        await self.update(False)

    @staticmethod
    def _unwrap_method_argument(value):
        return getattr(value, "Value", value)

    @staticmethod
    def _normalize_text_argument(value):
        """Normalize text from OPC UA clients that include literal quote marks."""
        value = str(OPCUAServer._unwrap_method_argument(value)).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1].strip()
        return value

    @staticmethod
    def _boolean_output(value: bool):
        return [ua.Variant(bool(value), ua.VariantType.Boolean)]

    @staticmethod
    def _string_output(value: str):
        return [ua.Variant(str(value), ua.VariantType.String)]

    async def _start_method(self, parent):
        await self.start_simulation()
        return self._boolean_output(True)

    async def _stop_method(self, parent):
        await self.stop_simulation()
        return self._boolean_output(True)

    async def _reset_method(self, parent):
        await self.reset_simulation()
        return self._boolean_output(True)

    async def _inject_fault_method(self, parent, fault_id, fault_type, target, magnitude, value, duration_hours):
        result = self.inject_fault(
            self._normalize_text_argument(fault_id),
            self._normalize_text_argument(fault_type),
            self._normalize_text_argument(target),
            float(self._unwrap_method_argument(magnitude)),
            float(self._unwrap_method_argument(value)),
            float(self._unwrap_method_argument(duration_hours)),
        )
        return self._boolean_output(result)

    async def _clear_fault_method(self, parent, fault_id):
        result = self.clear_fault(self._normalize_text_argument(fault_id))
        return self._boolean_output(result)

    async def _clear_all_faults_method(self, parent):
        result = self.clear_all_faults()
        return self._boolean_output(result)

    async def _list_faults_method(self, parent):
        return self._string_output(self.list_faults())

    def inject_fault(self, fault_id: str, fault_type: str, target: str, magnitude: float = 0.0, value: float = 0.0, duration_hours: float = 0.0) -> bool:
        fault_id = self._normalize_text_argument(fault_id)
        fault_type = self._normalize_text_argument(fault_type).lower()
        target = self._normalize_text_argument(target)
        fault_kind = FaultType(fault_type)
        if not fault_id:
            raise ValueError("fault_id must not be empty")
        if not target:
            raise ValueError("target must not be empty")
        if duration_hours < 0:
            raise ValueError("duration_hours must be >= 0")
        start = float(self.simulator.get_time_hours())
        duration = None if duration_hours == 0 else float(duration_hours)
        metadata = {"injection_source": "opcua", "operator_injected": True}
        if fault_kind is FaultType.PROCESS_DISTURBANCE:
            metadata["idv_index"] = self._resolve_idv_index(target)
        fault = Fault(fault_id=fault_id, fault_type=fault_kind, target=target, magnitude=float(magnitude), value=float(value) if fault_kind is FaultType.STUCK else None, start_time_hours=start, duration_hours=duration, metadata=metadata)
        self.fault_manager.add(fault)
        self._refresh_fault_count()
        self._emit_operator_fault_event("FaultInjected", fault)
        return True

    def clear_fault(self, fault_id: str) -> bool:
        fault = self.fault_manager.remove(self._normalize_text_argument(fault_id))
        self._refresh_fault_count()
        self._emit_operator_fault_event("FaultCleared", fault)
        sync_faults = getattr(self.simulator, "sync_faults", None)
        if callable(sync_faults):
            sync_faults()
        return True

    def clear_all_faults(self) -> bool:
        for fault_id in [fault.fault_id for fault in self.fault_manager.faults()]:
            self.clear_fault(fault_id)
        return True

    def _fault_status(self, fault: Fault, simulation_time_hours: float | None = None) -> str:
        """Return the OPC UA-facing lifecycle state for a registered fault."""
        current_time = float(
            self.simulator.get_time_hours()
            if simulation_time_hours is None
            else simulation_time_hours
        )
        if current_time < fault.start_time_hours:
            return "registered"
        if fault.duration_hours is None:
            return "active"
        if current_time < fault.start_time_hours + fault.duration_hours:
            return "active"
        return "expired"

    def list_faults(self) -> str:
        current_time = float(self.simulator.get_time_hours())
        return json.dumps(
            [
                {
                    "fault_id": fault.fault_id,
                    "fault_type": fault.fault_type.value,
                    "target": fault.target,
                    "magnitude": fault.magnitude,
                    "value": fault.value,
                    "start_time_hours": fault.start_time_hours,
                    "duration_hours": fault.duration_hours,
                    "status": self._fault_status(fault, current_time),
                    "metadata": dict(fault.metadata),
                }
                for fault in self.fault_manager.faults()
            ],
            sort_keys=True,
        )

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
        if self.fault_event_callback is not None:
            self.fault_event_callback({"event_type": event_type, "fault_id": fault.fault_id, "fault_type": fault.fault_type.value, "target": fault.target, "simulation_time_hours": self.simulator.get_time_hours(), "metadata": dict(fault.metadata)})

    def _handle_fault_event(self, event):
        if self.fault_event_callback is not None:
            self.fault_event_callback(event)

    async def sync_manipulated_variables(self):
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
        if self._time_node is not None:
            await self._time_node.write_value(float(self.simulator.get_time_hours()))
        if self._running_node is not None:
            await self._running_node.write_value(bool(running))
        if self._control_mode_node is not None:
            await self._control_mode_node.write_value(self._control_mode_name())
        if self._real_time_factor_node is not None:
            await self._real_time_factor_node.write_value(self._real_time_factor)
        if self._measurement_nodes:
            for node, value in zip(self._measurement_nodes, self.simulator.get_measurements()):
                await node.write_value(float(value))
        if self._mv_nodes:
            for node, value in zip(self._mv_nodes, self.simulator.get_manipulated_variables()):
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
        self._last_synced_mvs = [float(value) for value in self.simulator.get_manipulated_variables()]
        await self.update(False)

    async def _simulation_loop(self):
        while True:
            await asyncio.sleep(self._update_interval_seconds)
            steps = max(1, int(round(self._update_interval_seconds * self._real_time_factor)))
            for _ in range(steps):
                # External controllers own XMV writes. Apply the latest OPC UA
                # values before each process step so the command affects the
                # immediately following integration step.
                await self.sync_manipulated_variables()
                self.simulator.step()
            await self.update(True)

    async def stop(self):
        """Stop simulation and release the OPC UA server listener."""
        await self.stop_simulation()
        if self._server is not None:
            server = self._server
            self._server = None
            await server.stop()

    async def run(self):
        await self.start()
        await self.start_simulation()
        try:
            while True:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()
