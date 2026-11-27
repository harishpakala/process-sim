"""Local research service; one exclusive writer, persistent journal required."""
import argparse
import json
from pathlib import Path

from .aas_governance import AASGovernance
from .automation_manager import MultiContractAutomationManager
from .governance_api import create_app
from .graphdb_repository import GraphDBRepository
from .semantic_lifting import SemanticLiftingAdapter


def build_service(endpoint, journal, *, mode, evidence_file, remote_quiescent=False, embedded=False):
    from semantic.config import TARGETS
    from semantic.ontoutils import compute_uri
    from selira.language.parser.frontend import parse_safsl

    root = Path(__file__).resolve().parents[2]
    registrations = [(json.loads(instance.read_text(encoding="utf-8")),
                      SemanticLiftingAdapter(domain, json.loads(template.read_text(encoding="utf-8"))))
                     for domain, template, instance in TARGETS
                     if domain in ("assetinventory", "productcatalog")]
    if len(registrations) != 2:
        raise ValueError("Expected SC-01 registrations")
    if mode == "inspect":
        store = GraphDBRepository(endpoint, [str(compute_uri(d["id"])) for d, _ in registrations],
                                  native_mode=True)
        return store.inspect_adoption({str(compute_uri(d["id"])): a.lift_instance(d)
                                       for d, a in registrations})
    if mode == "qualify":
        from rdflib import Graph
        parts = {str(compute_uri(d["id"])): a.lift_instance(d) for d,a in registrations}
        store = GraphDBRepository(endpoint, list(parts), native_mode=True)
        inspection = store.inspect_adoption(parts)
        graph = Graph()
        for part in parts.values():
            graph += part
        flags = json.loads(Path(evidence_file).read_text(encoding="utf-8"))
        if (set(flags) != {"evidence_complete", "identity_normalized", "applicability_confirmed"}
                or not isinstance(flags["evidence_complete"], list)
                or any(not isinstance(x, str) for x in flags["evidence_complete"])
                or type(flags["identity_normalized"]) is not bool
                or type(flags["applicability_confirmed"]) is not bool):
            raise ValueError("Invalid evidence attestation")
        manager = MultiContractAutomationManager([(root / "contracts/SC-01.safsl",
                                                   root / "bindings/SC-01.json")])
        outcomes = [manager._evaluate(graph, entry, ttl, set(flags["evidence_complete"]),
                    flags["identity_normalized"], flags["applicability_confirmed"])
                    for entry, ttl in manager._contracts.values()]
        values = {o["verdict"] for o in outcomes}
        return {"inspection": inspection, "evidence": flags, "contracts": outcomes,
                "adoption_ready": inspection["eligible"] and "V" in values and values <= {"V", "NA"}}
    journal = Path(journal).resolve()
    if mode in ("recover", "reconcile") and not journal.is_file():
        raise ValueError("Recovery requires the original persistent journal")
    journal.parent.mkdir(parents=True, exist_ok=True)
    store = GraphDBRepository(endpoint, [str(compute_uri(d["id"])) for d, _ in registrations],
                              native_mode=True, journal_path=journal, delta_updates=True)
    def evidence(old, candidate):
        # Explicit operator-supplied research attestation, not independent evidence.
        flags = json.loads(Path(evidence_file).read_text(encoding="utf-8"))
        if set(flags) != {"evidence_complete", "identity_normalized", "applicability_confirmed"}:
            raise ValueError("Invalid evidence attestation")
        if (not isinstance(flags["evidence_complete"], list)
                or any(not isinstance(x, str) for x in flags["evidence_complete"])
                or type(flags["identity_normalized"]) is not bool
                or type(flags["applicability_confirmed"]) is not bool):
            raise ValueError("Invalid evidence attestation types")
        return flags
    if mode == "reconcile":
        try:
            return {"status": store.reconcile_pending(remote_quiescent=remote_quiescent)}
        finally:
            store._journal.close()
    try:
        if store.pending_commit() is not None:
            raise RuntimeError("Pending commit requires offline reconciliation")
        if mode == "initialize":
            store.initialize_empty()
        elif mode not in ("recover", "adopt"):
            raise ValueError("Unsupported startup mode")
        manager = MultiContractAutomationManager([(root / "contracts/SC-01.safsl",
                                                   root / "bindings/SC-01.json")], store=store)
        policies = {"LP-01": parse_safsl((root / "policies/LP-01.safsl").read_text(encoding="utf-8")).children[0]}
        if mode == "adopt":
            from rdflib import Graph
            documents = {d["id"]: d for d, _ in registrations}
            parts = {str(compute_uri(d["id"])): a.lift_instance(d) for d,a in registrations}
            graph = Graph()
            for part in parts.values():
                graph += part
            flags = evidence(graph, graph)
            outcomes = [manager._evaluate(graph, entry, ttl,
                        set(flags["evidence_complete"]), flags["identity_normalized"],
                        flags["applicability_confirmed"])
                        for entry, ttl in manager._contracts.values()]
            values = {o["verdict"] for o in outcomes}
            if "V" not in values or not values <= {"V", "NA"}:
                raise ValueError(f"Adoption not qualified: {outcomes}")
            store.adopt_qualified(documents, parts)
        service = AASGovernance(manager, registrations, policies,
                                recover=mode in ("recover", "adopt"), evidence_provider=evidence)
        if embedded:
            return service
        return create_app(aas_governance=service)
    except Exception:
        store._journal.close()
        raise


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--evidence-file", required=True)
    parser.add_argument("--mode", choices=["qualify", "inspect", "initialize", "recover", "adopt", "reconcile"], required=True)
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--exclusive-writer", action="store_true", required=True)
    parser.add_argument("--remote-quiescent", action="store_true")
    args = parser.parse_args()
    app = build_service(args.endpoint, args.journal, mode=args.mode, evidence_file=args.evidence_file, remote_quiescent=args.remote_quiescent)
    if args.mode in ('inspect', 'reconcile', 'qualify'):
        print(json.dumps(app, indent=2))
        return
    uvicorn.run(app, host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()
