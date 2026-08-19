"""OPC UA server adapter for a process-sim simulator.

The server is deliberately independent of the TEP implementation. It exposes
raw TEP variables first; semantic engineering names can be added by a later
namespace layer without changing the simulator backend.
"""

from __future__ import annotations

from typing import Optional


class OPCUAServer:
    """Expose a process simulator through an OPC UA server.

    The first implementation provides a small, stable namespace containing:
    ``Simulation.TimeHours``, ``Simulation.Running``, ``Measurements.XMEAS1..41``
    and ``ManipulatedVariables.XMV1..12``.

    Parameters
    ----------
    simulator:
        Object implementing the process-sim simulator boundary. A TEPAdapter
        can be passed directly.
    endpoint:
        OPC UA endpoint URL, e.g. ``opc.tcp://0.0.0.0:4840/process-sim/``.
    namespace_uri:
        Stable application namespace URI.
    """

    def __init__(
        self,
        simulator,
        endpoint: str = "opc.tcp://0.0.0.0:4840/process-sim/",
        namespace_uri: str = "urn:process-sim:opcua",
    ) -> None:
        self.simulator = simulator
        self.endpoint = endpoint
        self.namespace_uri = namespace_uri
        self._server = None
        self._namespace_index: Optional[int] = None
        self._time_node = None
        self._running_node = None
        self._measurement_nodes = []
        self._mv_nodes = []

    async def start(self) -> None:
        """Start the OPC UA server and publish the current simulator values."""
        try:
            from asyncua import Server, ua
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
        await self._time_node.set_writable(False)
        await self._running_node.set_writable(False)

        measurements = await tep.add_object(self._namespace_index, "Measurements")
        values = self.simulator.get_measurements()
        self._measurement_nodes = []
        for index, value in enumerate(values, start=1):
            node = await measurements.add_variable(
                self._namespace_index, f"XMEAS{index}", float(value)
            )
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

    async def update(self, running: bool = True) -> None:
        """Publish the simulator's current state to OPC UA nodes."""
        if self._server is None:
            raise RuntimeError("OPC UA server is not started")

        await self._time_node.write_value(float(self.simulator.get_time_hours()))
        await self._running_node.write_value(bool(running))

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

    async def stop(self) -> None:
        """Stop the OPC UA server if it is running."""
        if self._server is not None:
            await self._server.stop()
            self._server = None

    async def run(self) -> None:
        """Keep the OPC UA server alive until cancelled.

        This method intentionally does not advance the simulator. A later
        simulation-clock component will own stepping and call ``update()``.
        """
        if self._server is None:
            await self.start()

        import asyncio

        while True:
            await asyncio.sleep(1.0)
