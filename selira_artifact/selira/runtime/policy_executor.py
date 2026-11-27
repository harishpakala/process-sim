"""Execute registered Boolean policies using runtime bindings."""
import json
from pathlib import Path

from .contract_registry import load_registry
from .event_dispatcher import EventDispatcher
from .policy_evaluator import load_policy, evaluate_policy
from .runtime_binding import validate_binding, resolve_inputs, bind_outputs


class PolicyExecutor:
    def __init__(self, root):
        root = Path(root).resolve()
        entries = load_registry(root)
        self._policies = {}
        self._dispatcher = EventDispatcher(entries)
        for entry in entries:
            if entry["kind"] != "LP" or not entry["enabled"]:
                continue
            process = load_policy(root / entry["specification"])
            binding = json.loads((root / entry["binding"]).read_text(
                encoding="utf-8"))
            validate_binding(process, binding)
            self._policies[entry["id"]] = (process, binding)

    def _execute(self, entry, context):
        process, binding = self._policies[entry["id"]]
        inputs = resolve_inputs(process, binding, context)
        outputs = evaluate_policy(process, inputs)
        return bind_outputs(process, binding, outputs)

    def dispatch(self, event, context):
        return self._dispatcher.dispatch(event, context, self._execute)
