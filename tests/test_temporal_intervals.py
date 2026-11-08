"""Offline regression tests for temporal command interval semantics."""

import unittest
from datetime import datetime, timezone

from process_sim.api.temporal_intervals import (
    classify_observation, derive_fault_command_intervals,
)

RUN = "c2e5a121-99f8-4d19-b0b5-15cefe5bd611"
OTHER = "1c0b7e63-bce8-49ca-9f9a-4d9710cfd431"


def event(identifier, action, fault, time, run=RUN):
    return {
        "event_id": identifier, "run_id": run, "action": action,
        "fault_id": fault, "simulation_time_hours": time,
        "observed_at": datetime(2026, 11, 8, tzinfo=timezone.utc),
    }


class TemporalIntervalTests(unittest.TestCase):
    def test_closed_interval_and_boundary(self):
        result = derive_fault_command_intervals(RUN, [
            event("b", "clear", "IDV1", 2),
            event("a", "inject", "IDV1", 1),
        ])
        interval, = result["intervals"]
        self.assertEqual(interval["status"], "CLOSED")
        self.assertEqual(interval["startEventId"], "a")
        self.assertEqual([classify_observation(interval, x) for x in (0, 1, 1.9, 2, 3)],
                         ["BEFORE", "DURING", "DURING", "AFTER", "AFTER"])

    def test_overlapping_faults(self):
        result = derive_fault_command_intervals(RUN, [
            event("a", "inject", "IDV1", 1),
            event("b", "inject", "IDV2", 1.5),
            event("c", "clear", "IDV1", 2),
            event("d", "clear", "IDV2", 3),
        ])
        self.assertEqual(len(result["intervals"]), 2)
        self.assertFalse(result["anomalies"])

    def test_duplicate_commands_and_unmatched_clear(self):
        result = derive_fault_command_intervals(RUN, [
            event("a", "inject", "IDV1", 1),
            event("b", "inject", "IDV1", 1.5),
            event("c", "clear", "IDV2", 2),
        ])
        self.assertEqual([a["type"] for a in result["anomalies"]],
                         ["DUPLICATE_INJECT", "UNMATCHED_CLEAR"])
        self.assertEqual(result["intervals"][0]["status"], "OPEN_UNCONFIRMED")

    def test_incomplete_history_is_not_asserted_active(self):
        result = derive_fault_command_intervals(RUN, [
            event("a", "inject", "IDV1", 1),
        ], complete=False)
        self.assertEqual(classify_observation(result["intervals"][0], 2), "UNKNOWN")

    def test_mixed_run_rejected(self):
        with self.assertRaises(ValueError):
            derive_fault_command_intervals(RUN, [event("a", "inject", "IDV1", 1, OTHER)])

    def test_duplicate_identity_rejected(self):
        with self.assertRaises(ValueError):
            derive_fault_command_intervals(RUN, [
                event("a", "inject", "IDV1", 1),
                event("a", "clear", "IDV1", 2),
            ])

    def test_invalid_time_rejected(self):
        with self.assertRaises(ValueError):
            derive_fault_command_intervals(RUN, [event("a", "inject", "IDV1", float("nan"))])

    def test_unmatched_clear_only(self):
        result = derive_fault_command_intervals(RUN, [event("a", "clear", "IDV1", 2)])
        self.assertEqual(result["intervals"], [])
        self.assertEqual(result["anomalies"][0]["type"], "UNMATCHED_CLEAR")


if __name__ == "__main__":
    unittest.main()
