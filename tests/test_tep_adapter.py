"""Smoke and contract tests for the ProfBraatz TEP integration."""

import pytest

tep = pytest.importorskip("tep")

from process_sim.backends.tep import TEPAdapter


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
