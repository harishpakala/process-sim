"""Backward-compatible alias for process_sim.dtwise.shacl_planner.planning.state_machine."""
import importlib as _importlib
import sys as _sys
_sys.modules[__name__] = _importlib.import_module("process_sim.dtwise.shacl_planner.planning.state_machine")
