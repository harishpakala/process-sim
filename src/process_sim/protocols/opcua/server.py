"""OPC UA server adapter for a process-sim simulator."""

from __future__ import annotations

import asyncio
from typing import Callable


class OPCUAServer:
    """Expose a process simulator through an OPC UA server.

    ``event_callback`` is an optional integration hook for recording semantic
    OPC UA events without making the OPC UA protocol layer depend on the
    recording package. It is called when an OPC UA client changes an XMV value.
    """

    def __init__(
        self,
        simulator,
        endpoint="opc.tcp://0.0.0.0:4841/process-sim/",
        namespace_uri="urn:process-sim:opcua",
        real_time_factor=1.0,
        update_interval_seconds=1.0,
        event_callback: Callable[[int, float, float], None] | None = None,
    ):
        if real_time_factor <= 0:
            raise ValueError("real_time_factor must be > 0")
        if update_interval_seconds <= 0:
            raise ValueError("update_interval_seconds must be > 0")

        self.simulator = simulator
        self.endpoint = endpoint
        self.namespace_uri = namespace_uri
        self.event_callback = event_callback
        self._server = None
        self._namespace_index = None
        self._time_node = None
        self._running_node = None
        self._real_time_factor_node = None
        self._measurement_nodes = []
        self._mv_nodes = []
        self._last_synced_mvs = []
        self._simulation_task = None
        self._real_time_factor = float(real_time_factor)
        self._update_interval_seconds = float(update_interval_seconds)

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
        self._real_time_factor_node = await simulation.add_variable(self._namespace_index, "RealTimeFactor", self._real_time_factor)
        await self._time_node.set_read_only()
        await self._running_node.set_read_only()
        await self._real_time_factor_node.set_writable()
        await simulation.add_method(self._namespace_index, "Start", self._start_method)
        await simulation.add_method(self._namespace_index, "Stop", self._stop_method)
        await simulation.add_method(self._namespace_index, "Reset", self._reset_method)

        measurements = await tep.add_object(self._namespace_index, "Measurements")
        self._measurement_nodes = []
        for index, value in enumerate(self.simulator.get_measurements(), start=1):
            node = await measurements.add_variable(self._namespace_index, f"XMEAS{index}", float(value))
            await node.set_read_only()
            self._measurement_nodes.append(node)

        mvs = await tep.add_object(self._namespace_index, "ManipulatedVariables")
        self._mv_nodes = []
        for index, value in enumerate(self.simulator.get_manipulated_variables(), start=1):
            node = await mvs.add_variable(self._namespace_index, f"XMV{index}", float(value))
            await node.set_writable()
            self._mv_nodes.append(node)
        self._last_synced_mvs = [float(value) for value in self.simulator.get_manipulated_variables()]

        await self._server.start()
        await self.update(False)

    async def _start_method(self, parent):
        await self.start_simulation()

    async def _stop_method(self, parent):
        await self.stop_simulation()

    async def _reset_method(self, parent):
        await self.reset_simulation()

    async def update(self, running=False):
        await self._time_node.write_value(float(self.simulator.get_time_hours()))
        await self._running_node.write_value(bool(running))
        await self._real_time_factor_node.write_value(float(self._real_time_factor))
        for node, value in zip(self._measurement_nodes, self.simulator.get_measurements()):
            await node.write_value(float(value))
        for node, value in zip(self._mv_nodes, self.simulator.get_manipulated_variables()):
            await node.write_value(float(value))

    async def _sync_manipulated_variables(self):
        """Apply OPC UA XMV writes and report client-driven changes."""
        for index, node in enumerate(self._mv_nodes, start=1):
            value = float(await node.read_value())
            previous = self._last_synced_mvs[index - 1]
            if value != previous and self.event_callback is not None:
                self.event_callback(index, previous, value)
            self._last_synced_mvs[index - 1] = value
            self.simulator.set_manipulated_variable(index, value)

    async def _simulation_loop(self):
        try:
            while True:
                await self._sync_manipulated_variables()
                steps = max(1, int(round(self._update_interval_seconds * self._real_time_factor)))
                self.simulator.step(n_steps=steps)
                await self.update(True)
                await asyncio.sleep(self._update_interval_seconds)
        except asyncio.CancelledError:
            if self._server is not None:
                await self.update(False)
            raise

    async def start_simulation(self):
        if self._simulation_task is None or self._simulation_task.done():
            self._simulation_task = asyncio.create_task(self._simulation_loop())
        await self.update(True)

    async def stop_simulation(self):
        task, self._simulation_task = self._simulation_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self.update(False)

    async def reset_simulation(self):
        await self.stop_simulation()
        self.simulator.reset()
        self._last_synced_mvs = [float(value) for value in self.simulator.get_manipulated_variables()]
        await self.update(False)

    async def set_real_time_factor(self, value):
        value = float(value)
        if value <= 0:
            raise ValueError("real_time_factor must be > 0")
        self._real_time_factor = value
        await self._real_time_factor_node.write_value(value)

    async def stop(self):
        await self.stop_simulation()
        if self._server is not None:
            await self._server.stop()
            self._server = None

    async def run(self):
        if self._server is None:
            await self.start()
        while True:
            await asyncio.sleep(1.0)
