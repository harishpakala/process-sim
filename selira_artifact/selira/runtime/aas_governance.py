"""Exclusive in-memory AAS write coordinator; no durable transaction claims."""
from copy import deepcopy
from .graphdb_repository import rdf11_triples
import hashlib
import json
from threading import RLock

from rdflib import Graph

from .aas_candidate import stage_change
from .aas_messages import AASChangeResponse, ContractOutcome
from .terminal_activation import activate_policies


class AASGovernance:
    def __init__(self, manager, registrations, policies, *, evidence_provider=None, recover=False):
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
        if not recover and (version != 0 or len(current)):
            raise ValueError("Expected fresh governance manager")
        for document, adapter in registrations:
            key = document["id"]
            if key in self._documents:
                raise ValueError("Duplicate Submodel registration")
            self._documents[key] = deepcopy(document)
            self._adapters[key] = adapter
        if recover:
            self._blocked = True
            self._version = version
            self._recover()
            return
        initial = self._lift(self._documents)
        result = manager.submit(initial, expected_version=0,
                                **self._evidence(current, initial),
                                **self._native_state(self._documents))
        if not result["committed"]:
            raise ValueError("Initial snapshot not admitted")
        self._version = result["version"]
        self._blocked = False

    def _recover(self):
        """Recover only a coherent, currently qualified persisted snapshot.

        Caller must ensure exclusive ownership and no outstanding remote update.
        No write or version increment is performed.
        """
        pending = getattr(self._manager.store, "pending_commit", None)
        if pending is not None and pending() is not None:
            raise RuntimeError("Pending commit requires reconciliation before recovery")
        documents, parts, version, token = self._manager.store.native_snapshot()
        if set(documents) != set(self._adapters):
            raise ValueError("Persisted registration mismatch")
        _, expected = self._native_state(documents)["native_state"]
        if set(parts) != set(expected) or any(
            rdf11_triples(parts[key]) != rdf11_triples(expected[key]) for key in expected):
            raise ValueError("Persisted native/RDF coherence failure")
        graph = self._lift(documents)
        evidence = self._evidence(graph, graph)
        outcomes = [self._manager._evaluate(graph, entry, ttl,
                    set(evidence.get("evidence_complete", ())),
                    evidence.get("identity_normalized", False),
                    evidence.get("applicability_confirmed", False))
                    for entry, ttl in self._manager._contracts.values()]
        values = {outcome["verdict"] for outcome in outcomes}
        if "V" not in values or not values <= {"V", "NA"}:
            raise ValueError("Recovered state not qualified")
        self._documents = deepcopy(documents)
        self._version = version
        self._blocked = False

    def _lift(self, documents):
        graph = Graph()
        for key, document in documents.items():
            graph += self._adapters[key].lift_instance(document)
        return graph

    def _native_state(self, documents):
        if not hasattr(self._manager.store, "compare_and_commit_native"):
            return {}
        from semantic.ontoutils import compute_uri
        parts = {str(compute_uri(key)): self._adapters[key].lift_instance(doc)
                 for key, doc in documents.items()}
        return {"native_state": (deepcopy(documents), parts)}

    def _evidence(self, current, candidate):
        return self._provider(current, candidate) if self._provider else {}

    def snapshot(self):
        with self._lock:
            graph, version = self._manager.store.snapshot()
            if self._blocked or version != self._version:
                raise RuntimeError("Native state requires reconciliation")
            return deepcopy(self._documents), graph, version

    def submit(self, change):
        with self._lock:
            version = self._version
            def response(decision, committed=False, traces=(), outcomes=(), new_version=version):
                return AASChangeResponse(
                    message_id=change.header.message_id, decision=decision,
                    committed=committed, repository_version=new_version,
                    triggered_policies=[t.policy_id for t in traces],
                    evaluated_contracts=list(outcomes))
            context = {}
            lookup = getattr(self._manager.store, "request_outcome", None)
            if lookup is not None:
                fingerprint = hashlib.sha256(json.dumps(
                    change.model_dump(mode="json"), sort_keys=True,
                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
                source, message_id = change.header.source, change.header.message_id
                previous = lookup(source, message_id, fingerprint)
                if previous is not None:
                    if previous.get("pending"):
                        return response("DEFERRED")
                    return AASChangeResponse.model_validate(previous)
            if self._blocked:
                return response("DEFERRED")
            try:
                current, observed = self._manager.store.snapshot()
            except Exception:
                return response("DEFERRED")
            if observed != version:
                self._blocked = True
                return response("DEFERRED")
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
            if lookup is not None:
                def make_response(outcomes, next_version):
                    return response("ACCEPTED", True, traces,
                        [ContractOutcome(contract_id=r["id"], verdict=r["verdict"])
                         for r in outcomes.values()], next_version).model_dump(mode="json")
                context["request_context"] = (source, message_id, fingerprint, make_response)
            result = self._manager.submit(candidate, expected_version=version,
                                           **self._evidence(current, candidate),
                                           **self._native_state(documents), **context)
            if result["committed"]:
                self._documents = documents
                self._version = result["version"]
            elif result["reason"].startswith("Persistence unresolved") or result["version"] != version:
                self._blocked = True
            outcomes = [ContractOutcome(contract_id=r["id"], verdict=r["verdict"])
                        for r in result["contracts"].values()]
            decision = ("ACCEPTED" if result["committed"] else
                        "REJECTED" if result["verdict"] == "F" else "DEFERRED")
            return response(decision, result["committed"], traces, outcomes, self._version)
