#!/usr/bin/env python3
"""Audit evidence artifacts without inferring industrial authentication.

Manifest format:
{"artifacts":[{"contract":"SC-01","path":"evidence/a.json",
"sha256":"...","issuer":"...","verificationMethod":"...",
"verificationRecord":"..."}]}
Paths resolve below --evidence-root; no network calls are made.
"""

# Created: 2026-10-30
# Author: Harish
import argparse
import hashlib
import json
from pathlib import Path

SC = ("SC-01", "SC-02", "SC-03", "SC-04", "SC-05")
CAC = ("CAC-01", "CAC-02")


def inspect(manifest, evidence_root):
    root = Path(evidence_root).resolve()
    findings = []
    for item in manifest.get("artifacts", []):
        contract = item.get("contract")
        relative = item.get("path", "")
        candidate = (root / relative).resolve()
        safe = bool(relative) and candidate != root and root in candidate.parents
        exists = safe and candidate.is_file()
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest() if exists else None
        integrity = exists and digest == item.get("sha256")
        # A matching hash only proves consistency with the supplied manifest.
        # It does NOT establish who issued either artifact or manifest.
        verification = item.get("verificationRecord")
        authenticated = False  # No cryptographic signature/trust anchor verifier.
        findings.append({
            "contract": contract, "path": relative,
            "pathSafe": safe, "exists": bool(exists),
            "sha256MatchesManifest": bool(integrity),
            "issuerClaim": item.get("issuer"),
            "verificationMethodClaim": item.get("verificationMethod"),
            "verificationRecordPresent": bool(verification),
            "cryptographicallyAuthenticated": authenticated,
            "qualification": "U",
            "reason": ("Missing/unsafe artifact or hash mismatch" if not integrity
                       else "Integrity checked; issuer/trust anchor not independently verified"),
        })
    return {
        "evidenceAudit": findings,
        "allSCContractsRepresented": all(any(f["contract"] == sc for f in findings)
                                         for sc in SC),
        "engineeringCertification": "U",
        "authorization": False,
        "authenticatedEndToEndChain": False,
        "limitations": [
            "SHA-256 consistency is not provenance authentication",
            "Manifest issuer and verification fields are untrusted claims",
            "No signature, certificate chain, live OPC UA, or approval verified",
            "No source contract is upgraded to V by this audit",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--output", default="selira-evidence-audit.json")
    args = parser.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    output = inspect(manifest, args.evidence_root)
    Path(args.output).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print("Artifacts checked:", len(output["evidenceAudit"]))
    print("Authenticated end-to-end chain:", output["authenticatedEndToEndChain"])
    print("Wrote", args.output)


if __name__ == "__main__":
    main()
