"""Created: 2026-08-19
Author: Harish"""

from process_sim.faults import Fault, FaultManager, FaultType


def test_process_disturbance_target_resolution_without_tep_dependency():
    fault = Fault(
        fault_id="f1",
        fault_type=FaultType.PROCESS_DISTURBANCE,
        target="IDV6",
    )
    assert fault.target == "IDV6"


def test_fault_manager_keeps_process_disturbance_out_of_signal_transform():
    manager = FaultManager()
    manager.add(
        Fault(
            fault_id="f1",
            fault_type=FaultType.PROCESS_DISTURBANCE,
            target="IDV6",
        )
    )
    assert manager.apply("XMEAS9", 120.0, 0.0) == 120.0
    assert manager.apply("XMV10", 20.0, 0.0) == 20.0
