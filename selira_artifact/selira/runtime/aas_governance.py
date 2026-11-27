"""Exclusive in-memory AAS write coordinator; no durable transaction claims."""
from copy import deepcopy
from threading import RLock

from rdflib import Graph

from .aas_candidate import stage_change
from .aas_messages import AASChangeResponse, ContractOutcome
from .terminal_activation import activate_policies


class AASGovernance:
    def __init__(self, manager, registrations, policies, *, evidence_provider=None):
        """registrations contains (native document, trusted lifting adapter) pairs.

        Manager must be fresh and exclusively owned by this coordinator.
        Initial documents are admitted using the same governance engine.
        """
        self._manager = manager
        self._lock = RLock()
        self._policies = deepcopy(policies)
        self._provider = evidence_provider
        self._documents = {}
        self._adapters = {}
        current, version = manager.store.snapshot()
        if version != 0 or len(current):
            raise ValueError("Expected fresh governance manager")
        for document, adapter in registrations:
            key = document["id"]
            if key in self._documents:
                raise ValueError("Duplicate Submodel registration")
            self._documents[key] = deepcopy(document)
            self._adapters[key] = adapter
        initial = self._lift(self._documents)
        result = manager.submit(initial, expected_version=0,
                                **self._evidence(current, initial))
        if not result["committed"]:
            raise ValueError("Initial snapshot not admitted")

    def _lift(self, documents):
        graph = Graph()
        for key, document in documents.items():
            graph += self._adapters[key].lift_instance(document)
        return graph

    def _evidence(self, current, candidate):
        return self._provider(current, candidate) if self._provider else {}

    def snapshot(self):
        with self._lock:
            graph, version = self._manager.store.snapshot()
            return deepcopy(self._documents), graph, version

    def submit(self, change):
        with self._lock:
            current, version = self._manager.store.snapshot()
            def response(decision, committed=False, traces=(), outcomes=(), new_version=version):
                return AASChangeResponse(
                    message_id=change.header.message_id, decision=decision,
                    committed=committed, repository_version=new_version,
                    triggered_policies=[t.policy_id for t in traces],
                    evaluated_contracts=list(outcomes))
            if change.operation.expected_version != version:
                return response("DEFERRED")
            key = change.domain.submodel_id
            if key not in self._documents:
                raise ValueError("Unregistered Submodel")
            adapter = self._adapters[key]
            staged = stage_change(self._documents[key], change, adapter)
            traces = activate_policies(self._policies, template_id=adapter.template_id,
                                       candidate=staged, intent=change.policy)
            documents = dict(self._documents)
            documents[key] = staged.document
            candidate = self._lift(documents)
            # Full validation preserves all enabled contracts, including SC-01.
            # LP activation never bypasses the existing admission gate.
            result = self._manager.submit(candidate, expected_version=version,
                                           **self._evidence(current, candidate))
            if result["committed"]:
                self._documents = documents
            outcomes = [ContractOutcome(contract_id=r["id"], verdict=r["verdict"])
                        for r in result["contracts"].values()]
            decision = ("ACCEPTED" if result["committed"] else
                        "REJECTED" if result["verdict"] == "F" else "DEFERRED")
            return response(decision, result["committed"], traces, outcomes, result["version"])
