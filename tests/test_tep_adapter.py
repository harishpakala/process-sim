"""Smoke and contract tests for the ProfBraatz TEP integration."""

import pytest

tep = pytest.importorskip("tep")

from process_sim.backends.tep import TEPAdapter
from process_sim.faults import Fault, FaultManager, FaultType


def test_tep_adapter_initializes_with_expected_dimensions():
    sim = TEPAdapter(random_seed=123)
    sim.reset()

    assert sim.get_measurements().shape == (41,)
    assert sim.get_manipulated_variables().shape == (12,)
    assert sim.get_states().shape == (50,)
    assert sim.get_disturbances().shape == (20,)
    assert sim.get_time_hours() == 0.0


def test_tep_adapter_advances_one_native_step():
    sim = TEPAdapter(random_seed=123)
    sim.reset()

    running = sim.step()

    assert running is True
    assert sim.get_time_hours() == pytest.approx(1.0 / 3600.0)


def test_tep_adapter_exposes_idv6():
    sim = TEPAdapter(random_seed=123)
    sim.reset()

    sim.set_disturbance(6, 1)

    assert 6 in sim.active_disturbances()
    assert sim.disturbance_name(6) == "a_feed_loss_step"


def test_tep_adapter_batch_simulation():
    sim = TEPAdapter(random_seed=123)
    sim.reset()

    result = sim.simulate(
        duration_hours=1.0 / 3600.0,
        disturbances={6: (0.0, 1)},
    )

    assert result.measurements.shape[1] == 41
    assert result.manipulated_vars.shape[1] == 12
    assert result.states.shape[1] == 50


def test_sensor_fault_is_visible_to_native_controller_input():
    manager = FaultManager()
    manager.add(
        Fault(
            fault_id="reactor-temperature-bias",
            fault_type=FaultType.BIAS,
            target="XMEAS9",
            magnitude=5.0,
            start_time_hours=0.0,
            duration_hours=1.0 / 3600.0,
        )
    )
    sim = TEPAdapter(random_seed=123, fault_manager=manager)
    sim.reset()

    class SpyController:
        def __init__(self):
            self.received_xmeas = None

        def calculate(self, xmeas, xmv, step):
            self.received_xmeas = list(xmeas)
            return xmv

    spy = SpyController()
    sim.simulator.controller = spy
    native_xmeas9 = float(sim.simulator.get_measurements()[8])

    sim.step()

    assert spy.received_xmeas[8] == pytest.approx(native_xmeas9 + 5.0)


def test_external_control_mode_uses_manual_tep_control():
    sim = TEPAdapter(random_seed=123, control_mode="manual")
    sim.reset()

    assert sim.control_mode == "manual"
    assert sim.external_control is True
    assert sim.simulator.control_mode.value == "manual"

    sim.set_manipulated_variable(10, 25.0)
    sim.step()

    assert sim.get_manipulated_variables()[9] == pytest.approx(25.0)


def test_invalid_control_mode_is_rejected():
    with pytest.raises(ValueError, match="control_mode"):
        TEPAdapter(random_seed=123, control_mode="not-a-mode")


def test_fault_lifecycle_events_are_emitted_at_simulation_boundaries():
    manager = FaultManager()
    manager.add(
        Fault(
            fault_id="idv6-window",
            fault_type=FaultType.PROCESS_DISTURBANCE,
            target="IDV6",
            start_time_hours=0.0,
            duration_hours=1.0 / 3600.0,
        )
    )
    events = []
    sim = TEPAdapter(random_seed=123, fault_manager=manager, fault_event_sink=events.append)
    sim.reset()

    sim.sync_faults()
    assert events[0]["event_type"] == "FaultActivated"
    assert events[0]["simulation_time_hours"] == pytest.approx(0.0)
    assert 6 in sim.active_disturbances()

    sim.step()
    assert sim.get_time_hours() == pytest.approx(1.0 / 3600.0)
    assert events[-1]["event_type"] == "FaultDeactivated"
    assert events[-1]["simulation_time_hours"] == pytest.approx(1.0 / 3600.0)
    assert 6 not in sim.active_disturbances()


def test_fault_layer_restores_preexisting_native_disturbance():
    manager = FaultManager()
    manager.add(
        Fault(
            fault_id="idv6-window",
            fault_type=FaultType.PROCESS_DISTURBANCE,
            target="IDV6",
            start_time_hours=0.0,
            duration_hours=1.0 / 3600.0,
        )
    )
    sim = TEPAdapter(random_seed=123, fault_manager=manager)
    sim.reset()
    sim.set_disturbance(6, 1)

    sim.sync_faults()
    sim.step()

    assert 6 in sim.active_disturbances()
