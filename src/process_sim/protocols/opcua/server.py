"""OPC UA server adapter for a process-sim simulator."""

from __future__ import annotations

import asyncio
from typing import Optional


class OPCUAServer:
    """Expose a process simulator through an OPC UA server.

    The namespace contains raw TEP variables first. Simulation stepping is
    owned by a background task controlled through OPC UA methods so clients
    can start, stop, and reset the simulation without coupling the process
    model to the OPC UA transport.
    """

    def __init__(
        self,
        simulator,
        endpoint: str = "opc.tcp://0.0.0.0:4841/process-sim/",
        namespace_uri: str = "urn:process-sim:opcua",
        real_time_factor: float = 1.0,
        update_interval_seconds: float = 1.0,
    ) -> None:
        if real_time_factor <= 0:
            raise ValueError("real_time_factor must be > 0")
        if update_interval_seconds <= 0:
            raise ValueError("update_interval_seconds must be > 0")

        self.simulator = simulator
        self.endpoint = endpoint
        self.namespace_uri = namespace_uri
        self.real_time_factor = float(real_time_factor)
        self.update_interval_seconds = float(update_interval_seconds)
        self._server = None
        self._namespace_index: Optional[int] = None
        self._time_node = None
        self._running_node = None
        self._rtf_node = None
        self._measurement_nodes = []
        self._mv_nodes = []
        self._simulation_task: Optional[asyncio.Task] = None

    @property
    def running(self) -> bool:
        """Return whether the background simulation task is active."""
        return self._simulation_task is not None and not self._simulation_task.done()

    async def start(self) -> None:
        """Start the OPC UA server without automatically starting simulation."""
        try:
            from asyncua import Server
        except ImportError as exc:
            raise ImportError(
                "OPCUAServer requires 'asyncua'. Install it with "
                "'pip install asyncua'."
            ) from exc

        self._server = Server()
        await self._server.init()
        self._server.set_endpoint(self.endpoint)
        self._namespace_index = await self._server.register_namespace(
            self.namespace_uri
        )

        objects = self._server.nodes.objects
        tep = await objects.add_object(self._namespace_index, "TEP")

        simulation = await tep.add_object(self._namespace_index, "Simulation")
        self._time_node = await simulation.add_variable(
            self._namespace_index, "TimeHours", float(self.simulator.get_time_hours())
        )
        self._running_node = await simulation.add_variable(
            self._namespace_index, "Running", False
        )
        self._rtf_node = await simulation.add_variable(
            self._namespace_index, "RealTimeFactor", self.real_time_factor
        )
        await self._time_node.set_read_only()
        await self._running_node.set_read_only()
        await self._rtf_node.set_writable()

        async def start_callback(_parent):
            await self.start_simulation()
            return []

        async def stop_callback(_parent):
            await self.stop_simulation()
            return []

        async def reset_callback(_parent):
            await self.reset_simulation()
            return []

        await simulation.add_method(
            self._namespace_index, "Start", start_callback
        )
        await simulation.add_method(
            self._namespace_index, "Stop", stop_callback
        )
        await simulation.add_method(
            self._namespace_index, "Reset", reset_callback
        )

        measurements = await tep.add_object(self._namespace_index, "Measurements")
        values = self.simulator.get_measurements()
        self._measurement_nodes = []
        for index, value in enumerate(values, start=1):
            node = await measurements.add_variable(
                self._namespace_index, f"XMEAS{index}", float(value)
            )
            await node.set_read_only()
            self._measurement_nodes.append(node)

        mvs = await tep.add_object(self._namespace_index, "ManipulatedVariables")
        values = self.simulator.get_manipulated_variables()
        self._mv_nodes = []
        for index, value in enumerate(values, start=1):
            node = await mvs.add_variable(
                self._namespace_index, f"XMV{index}", float(value)
            )
            await node.set_writable()
            self._mv_nodes.append(node)

        await self._server.start()
        await self.update(running=False)

    async def update(self, running: Optional[bool] = None) -> None:
        """Publish the simulator's current state to OPC UA nodes."""
        if self._server is None:
            raise RuntimeError("OPC UA server is not started")

        if running is None:
            running = self.running

        await self._time_node.write_value(float(self.simulator.get_time_hours()))
        await self._running_node.write_value(bool(running))
        await self._rtf_node.write_value(float(self.real_time_factor))

        measurements = self.simulator.get_measurements()
        if len(measurements) != len(self._measurement_nodes):
            raise RuntimeError("Simulator measurement count changed after startup")
        for node, value in zip(self._measurement_nodes, measurements):
            await node.write_value(float(value))

        mvs = self.simulator.get_manipulated_variables()
        if len(mvs) != len(self._mv_nodes):
            raise RuntimeError("Simulator MV count changed after startup")
        for node, value in zip(self._mv_nodes, mvs):
            await node.write_value(float(value))

    async def step(self, n_steps: int = 1) -> None:
        """Advance the simulator and immediately publish the new state."""
        if self._server is None:
            raise RuntimeError("OPC UA server is not started")
        if n_steps < 1:
            raise ValueError("n_steps must be >= 1")

        self.simulator.step(n_steps=n_steps)
        await self.update(running=self.running)

    async def start_simulation(self) -> None:
        """Start background simulation if it is not already running."""
        if self._server is None:
            raise RuntimeError("OPC UA server is not started")
        if self.running:
            return

        self._simulation_task = asyncio.create_task(self._simulation_loop())
        await self.update(running=True)

    async def stop_simulation(self) -> None:
        """Pause the simulation while keeping the OPC UA server available."""
        task = self._simulation_task
        if task is None:
            await self.update(running=False)
            return

        self._simulation_task = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await self.update(running=False)

    async def reset_simulation(self) -> None:
        """Stop and reset the simulator to its initial state."""
        await self.stop_simulation()
        self.simulator.reset()
        await self.update(running=False)

    async def _simulation_loop(self) -> None:
        """Advance and publish the simulator until stopped or cancelled."""
        steps_per_update = max(
            1,
            int(round(self.update_interval_seconds * self.real_time_factor)),
        )

        try:
            while True:
                self.simulator.step(n_steps=steps_per_update)
                await self.update(running=True)
                await asyncio.sleep(self.update_interval_seconds)
        except asyncio.CancelledError:
            raise

    async def run_simulation(
        self,
        real_time_factor: Optional[float] = None,
        update_interval_seconds: Optional[float] = None,
    ) -> None:
        """Start simulation and wait until it is stopped."""
        if real_time_factor is not None:
            if real_time_factor <= 0:
                raise ValueError("real_time_factor must be > 0")
            self.real_time_factor = float(real_time_factor)
        if update_interval_seconds is not None:
            if update_interval_seconds <= 0:
                raise ValueError("update_interval_seconds must be > 0")
            self.update_interval_seconds = float(update_interval_seconds)

        if self._server is None:
            await self.start()
        await self.start_simulation()
        await self._simulation_task

    async def stop(self) -> None:
        """Stop simulation and the OPC UA server."""
        await self.stop_simulation()
        if self._server is not None:
            await self._server.stop()
            self._server = None

    async def run(self) -> None:
        """Keep the OPC UA server alive without starting the simulation."""
        if self._server is None:
            await self.start()

        while True:
            await asyncio.sleep(1.0)
