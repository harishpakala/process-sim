import asyncio

import pytest

from process_sim.protocols.opcua import OPCUAServer


class FakeSimulator:
    def __init__(self):
        self.time = 0.0
        self.measurements = [float(i) for i in range(1, 42)]
        self.mvs = [float(i) for i in range(1, 13)]
        self.writes = {}

    def get_time_hours(self):
        return self.time

    def get_measurements(self):
        return self.measurements

    def get_manipulated_variables(self):
        return self.mvs

    def set_manipulated_variable(self, index, value):
        self.writes[index] = value


@pytest.mark.asyncio
async def test_opcua_namespace_and_values():
    pytest.importorskip("asyncua")

    simulator = FakeSimulator()
    server = OPCUAServer(
        simulator,
        endpoint="opc.tcp://127.0.0.1:48491/process-sim-test/",
    )

    await server.start()
    try:
        assert len(server._measurement_nodes) == 41
        assert len(server._mv_nodes) == 12
        assert await server._time_node.read_value() == 0.0
        assert await server._measurement_nodes[8].read_value() == 9.0
        assert await server._mv_nodes[9].read_value() == 10.0

        await server._mv_nodes[0].write_value(42.5)
        await server.sync_manipulated_variables()
        assert simulator.writes[1] == 42.5
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_update_publishes_current_values():
    pytest.importorskip("asyncua")

    simulator = FakeSimulator()
    server = OPCUAServer(
        simulator,
        endpoint="opc.tcp://127.0.0.1:48492/process-sim-test/",
    )

    await server.start()
    try:
        simulator.time = 1.5
        simulator.measurements[8] = 123.0
        await server.update(running=True)

        assert await server._time_node.read_value() == 1.5
        assert await server._running_node.read_value() is True
        assert await server._measurement_nodes[8].read_value() == 123.0
    finally:
        await server.stop()
