from process_sim.faults import Fault, FaultManager, FaultType


def test_bias_fault_is_applied_when_active():
    manager = FaultManager()
    manager.add(
        Fault(
            fault_id="f1",
            fault_type=FaultType.BIAS,
            target="XMEAS9",
            magnitude=5.0,
            start_time_hours=1.0,
        )
    )

    assert manager.apply("XMEAS9", 120.0, 0.5) == 120.0
    assert manager.apply("XMEAS9", 120.0, 1.0) == 125.0


def test_stuck_fault_overrides_signal_for_duration():
    manager = FaultManager()
    manager.add(
        Fault(
            fault_id="f2",
            fault_type=FaultType.STUCK,
            target="XMV10",
            value=20.0,
            start_time_hours=1.0,
            duration_hours=0.5,
        )
    )

    assert manager.apply("XMV10", 16.0, 1.25) == 20.0
    assert manager.apply("XMV10", 16.0, 1.5) == 16.0


def test_process_disturbance_is_visible_but_not_signal_transformed():
    manager = FaultManager()
    fault = Fault(
        fault_id="f3",
        fault_type=FaultType.PROCESS_DISTURBANCE,
        target="IDV6",
        magnitude=1.0,
        start_time_hours=2.0,
    )
    manager.add(fault)

    assert manager.active_faults(2.0) == (fault,)
    assert manager.apply("IDV6", 0.0, 2.0) == 0.0
