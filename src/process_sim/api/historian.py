"""Process-local OPC UA time-series collector, independent of Vue navigation."""
from __future__ import annotations
import asyncio
from collections import deque
from threading import Event, Lock, Thread
from time import sleep

_lock = Lock()
_samples = deque(maxlen=1800)
_latest = None
_error = None
_started = False


def _run():
    global _latest, _error
    from process_sim.api.opcua_client import snapshot
    while True:
        try:
            result = asyncio.run(snapshot())
            time = float(result["simulation"]["TimeHours"])
            with _lock:
                if _samples and time < _samples[-1]["time"]:
                    _samples.clear()
                if not _samples or time != _samples[-1]["time"]:
                    _samples.append({"time": time, "measurements": result["measurements"], "manipulatedVariables": result["manipulatedVariables"]})
                _latest = result
                _error = None
        except Exception as exc:
            with _lock:
                _error = str(exc)
                _latest = None
        sleep(2)


def start():
    global _started
    with _lock:
        if _started:
            return
        _started = True
    Thread(target=_run, name="tep-historian", daemon=True).start()


def history():
    with _lock:
        return {"samples": list(_samples), "snapshot": _latest, "error": _error}
