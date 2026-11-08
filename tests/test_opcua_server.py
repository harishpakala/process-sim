"""Created: 2026-08-19
Author: Harish"""

import asyncio
import json

import pytest

from process_sim.faults import Fault, FaultType
from process_sim.protocols.opcua import OPCUAServer


class FakeSimulator:
    def __init__(self):
        self.time = 0.0
        self.measurements = [float(i) for i in range(1, 42)]
        self.mvs = [float(i) for i in range(1, 13)]
        self.writes = {}
        self.fault_manager = None
        self.external_control = True

    def get_time_hours(self):
        return self.time

    def get_measurements(self):
        return self.measurements

    def get_manipulated_variables(self):
        return self.mvs

    def set_manipulated_variable(self, index, value):
        self.writes[index] = value

    def configure_faults(self, fault_manager, fault_event_sink=None):
        self.fault_manager = fault_manager
        self.fault_event_sink = fault_event_sink

    def reset(self):
        self.time = 0.0


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
        assert await server._control_mode_node.read_value() == "external_opcua"
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
        assert await server._control_mode_node.read_value() == "external_opcua"
        assert await server._measurement_nodes[8].read_value() == 123.0
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_opcua_method_unwraps_variant_arguments():
    from asyncua import ua

    simulator = FakeSimulator()
    server = OPCUAServer(simulator)

    result = await server._inject_fault_method(
        None,
        ua.Variant("operator-bias-variant", ua.VariantType.String),
        ua.Variant("bias", ua.VariantType.String),
        ua.Variant("XMEAS9", ua.VariantType.String),
        ua.Variant(5.0, ua.VariantType.Double),
        ua.Variant(0.0, ua.VariantType.Double),
        ua.Variant(0.5, ua.VariantType.Double),
    )
    assert result[0].Value is True

    configured = json.loads(server.list_faults())
    assert configured[0]["fault_id"] == "operator-bias-variant"
    assert configured[0]["magnitude"] == 5.0
    assert configured[0]["duration_hours"] == 0.5


def test_opcua_fault_injection_and_clear():
    simulator = FakeSimulator()
    events = []
    server = OPCUAServer(
        simulator,
        fault_event_callback=events.append,
    )

    assert server.inject_fault(
        "operator-bias-1",
        "bias",
        "XMEAS9",
        magnitude=5.0,
        duration_hours=0.5,
    )

    configured = json.loads(server.list_faults())
    assert configured[0]["fault_id"] == "operator-bias-1"
    assert configured[0]["start_time_hours"] == 0.0
    assert configured[0]["duration_hours"] == 0.5
    assert configured[0]["status"] == "active"
    assert configured[0]["metadata"]["injection_source"] == "opcua"
    assert events[0]["event_type"] == "FaultInjected"

    assert server.clear_fault("operator-bias-1")
    assert json.loads(server.list_faults()) == []
    assert events[-1]["event_type"] == "FaultCleared"


def test_opcua_fault_status_transitions():
    simulator = FakeSimulator()
    server = OPCUAServer(simulator)

    server.fault_manager.add(
        Fault(
            fault_id="future-fault",
            fault_type=FaultType.BIAS,
            target="XMEAS9",
            magnitude=5.0,
            start_time_hours=1.0,
            duration_hours=0.5,
        )
    )

    simulator.time = 0.5
    assert json.loads(server.list_faults())[0]["status"] == "registered"

    simulator.time = 1.0
    assert json.loads(server.list_faults())[0]["status"] == "active"

    simulator.time = 1.5
    assert json.loads(server.list_faults())[0]["status"] == "expired"

    simulator.time = 2.0
    assert json.loads(server.list_faults())[0]["status"] == "expired"


def test_opcua_indefinite_fault_remains_active():
    simulator = FakeSimulator()
    server = OPCUAServer(simulator)

    server.inject_fault("indefinite-bias", "bias", "XMEAS9", magnitude=5.0)

    simulator.time = 10.0
    configured = json.loads(server.list_faults())
    assert configured[0]["status"] == "active"
    assert configured[0]["duration_hours"] is None


def test_opcua_process_disturbance_maps_to_idv():
    simulator = FakeSimulator()
    server = OPCUAServer(simulator)

    assert server.inject_fault(
        "operator-idv-6",
        "process_disturbance",
        "IDV6",
    )

    configured = json.loads(server.list_faults())
    assert configured[0]["metadata"]["idv_index"] == 6
    assert configured[0]["fault_type"] == "process_disturbance"


def test_opcua_fault_validation():
    simulator = FakeSimulator()
    server = OPCUAServer(simulator)

    with pytest.raises(ValueError, match="fault_id"):
        server.inject_fault("", "bias", "XMEAS9")

    with pytest.raises(ValueError, match="duration_hours"):
        server.inject_fault("fault", "bias", "XMEAS9", duration_hours=-1.0)

    with pytest.raises(ValueError, match="IDV1..IDV20"):
        server.inject_fault("fault", "process_disturbance", "IDV21")
