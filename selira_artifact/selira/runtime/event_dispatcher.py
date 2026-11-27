"""Synchronous, per-instance policy activation; no external event bus."""
from collections import defaultdict


class EventDispatcher:
    def __init__(self, entries):
        self._subscriptions = defaultdict(list)
        edges = defaultdict(set)
        for entry in entries:
            if entry["kind"] != "LP" or not entry["enabled"]:
                continue
            event = entry["activation"]["event"]
            produced = entry["produces"]
            self._subscriptions[event].append(entry)
            edges[event].add(produced)

        def visit(event, active, complete):
            if event in active:
                raise ValueError(f"Cyclic policy activation: {event}")
            if event in complete:
                return
            active.add(event)
            for successor in edges.get(event, ()):
                visit(successor, active, complete)
            active.remove(event)
            complete.add(event)

        complete = set()
        for event in edges:
            visit(event, set(), complete)

    def policies_for(self, event):
        """Registry order is the deterministic order for a single event."""
        return tuple(self._subscriptions.get(event, ()))

    def dispatch(self, event, context, execute):
        """Execute policies against one isolated instance context.

        execute(entry, context) returns a mapping of new data points.
        Errors propagate; no partial context is returned to the caller.
        """
        working = dict(context)
        trace = []
        pending = [event]
        emitted = {event}
        while pending:
            current = pending.pop(0)
            for entry in self.policies_for(current):
                outputs = execute(entry, dict(working))
                if not isinstance(outputs, dict):
                    raise ValueError("Expected policy output mapping")
                if working.keys() & outputs.keys():
                    raise ValueError("Policy output overwrites existing context")
                working.update(outputs)
                trace.append((current, entry["id"]))
                produced = entry["produces"]
                if produced in emitted:
                    raise ValueError(f"Ambiguous repeated event: {produced}")
                emitted.add(produced)
                pending.append(produced)
        return working, tuple(trace)
