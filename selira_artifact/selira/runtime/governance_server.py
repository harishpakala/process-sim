"""Local research service; one exclusive writer, persistent journal required."""
import argparse
import json
from pathlib import Path

from .aas_governance import AASGovernance
from .automation_manager import MultiContractAutomationManager
from .governance_api import create_app
from .graphdb_repository import GraphDBRepository
from .semantic_lifting import SemanticLiftingAdapter


def build_service(endpoint, journal, *, mode, evidence_file):
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
    journal = Path(journal).resolve()
    if mode == "recover" and not journal.is_file():
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
    try:
        if store.pending_commit() is not None:
            raise RuntimeError("Pending commit requires offline reconciliation")
        if mode == "initialize":
            store.initialize_empty()
        elif mode != "recover":
            raise ValueError("Unsupported startup mode")
        manager = MultiContractAutomationManager([(root / "contracts/SC-01.safsl",
                                                   root / "bindings/SC-01.json")], store=store)
        policies = {"LP-01": parse_safsl((root / "policies/LP-01.safsl").read_text(encoding="utf-8")).children[0]}
        service = AASGovernance(manager, registrations, policies,
                                recover=mode == "recover", evidence_provider=evidence)
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
    parser.add_argument("--mode", choices=["inspect", "initialize", "recover"], required=True)
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--exclusive-writer", action="store_true", required=True)
    args = parser.parse_args()
    app = build_service(args.endpoint, args.journal, mode=args.mode, evidence_file=args.evidence_file)
    if args.mode == 'inspect':
        print(json.dumps(app, indent=2))
        return
    uvicorn.run(app, host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()
