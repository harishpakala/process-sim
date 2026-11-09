"""Regression tests for historian run finalization on API shutdown."""
import unittest
from unittest.mock import Mock, patch

from process_sim.api import historian


class HistorianShutdownTests(unittest.TestCase):
    def setUp(self):
        self.original = (
            historian._worker, historian._started, historian._persisted_run,
            historian._stop_event.is_set(),
        )
        historian._stop_event.clear()

    def tearDown(self):
        historian._worker, historian._started, historian._persisted_run, was_set = self.original
        if was_set:
            historian._stop_event.set()
        else:
            historian._stop_event.clear()

    def test_graceful_stop_finalizes_persisted_run_once(self):
        worker = Mock()
        worker.is_alive.return_value = False
        historian._worker = worker
        historian._started = True
        historian._persisted_run = "test-run"
        with patch("process_sim.api.timeseries.end_run") as end_run:
            historian.stop()
            end_run.assert_called_once_with("test-run", "application_shutdown")
            worker.join.assert_called_once_with(10)
            self.assertTrue(historian._stop_event.is_set())
            historian.stop()
            end_run.assert_called_once()

    def test_timeout_does_not_finalize_run(self):
        worker = Mock()
        worker.is_alive.return_value = True
        historian._worker = worker
        historian._started = True
        historian._persisted_run = "test-run"
        with patch("process_sim.api.timeseries.end_run") as end_run:
            with self.assertRaises(TimeoutError):
                historian.stop(timeout=0.01)
            end_run.assert_not_called()
        self.assertEqual(historian._persisted_run, "test-run")

    def test_no_persisted_run_needs_no_finalization(self):
        worker = Mock()
        worker.is_alive.return_value = False
        historian._worker = worker
        historian._started = True
        historian._persisted_run = None
        with patch("process_sim.api.timeseries.end_run") as end_run:
            historian.stop()
            end_run.assert_not_called()
        self.assertFalse(historian._started)

    def test_database_failure_is_not_silenced(self):
        worker = Mock()
        worker.is_alive.return_value = False
        historian._worker = worker
        historian._started = True
        historian._persisted_run = "test-run"
        with patch("process_sim.api.timeseries.end_run", side_effect=RuntimeError("db unavailable")):
            with self.assertRaisesRegex(RuntimeError, "db unavailable"):
                historian.stop()
        self.assertEqual(historian._persisted_run, "test-run")


if __name__ == "__main__":
    unittest.main()
