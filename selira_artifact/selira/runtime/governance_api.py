"""HTTP adapter for the existing versioned governance coordinator.

Local, synchronous research service. Evidence is supplied by a server-side
provider, never accepted as an attestation from the HTTP request.
"""
from typing import Literal
from .aas_messages import AASChangeRequest, AASChangeResponse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from rdflib import Graph, URIRef, Literal as RDFLiteral


class Term(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["iri", "literal"]
    value: str

    def rdf(self):
        if self.kind == "iri":
            return iri(self.value)
        return RDFLiteral(self.value)


def iri(value):
    from urllib.parse import urlsplit
    if not urlsplit(value).scheme or any(c.isspace() or c in '<>"{}|^\x60\\' for c in value):
        raise ValueError("Expected absolute IRI")
    return URIRef(value)


class Triple(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    subject: str
    predicate: str
    object: Term

    def rdf(self):
        return iri(self.subject), iri(self.predicate), self.object.rdf()


class ChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_version: int = Field(ge=0)
    additions: list[Triple] = Field(default_factory=list)
    deletions: list[Triple] = Field(default_factory=list)


def create_app(manager=None, *, evidence_provider=None, aas_governance=None):
    """Inject a coordinator and optional trusted snapshot evidence provider.

    Provider receives (current, candidate) graphs and returns submit keyword
    attestations. Without a provider, the existing manager defaults apply.
    """
    if (manager is None) == (aas_governance is None):
        raise ValueError("Choose exactly one repository write coordinator")
    app = FastAPI(title="SELiRA Automation Manager", version="0.1.0")

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "version": (aas_governance.snapshot()[2]
                if aas_governance is not None else manager.store.snapshot()[1])}

    @app.post("/api/v1/changes/aas", response_model=AASChangeResponse)
    def submit_aas(change: AASChangeRequest):
        if aas_governance is None:
            raise HTTPException(status_code=409, detail="Native AAS governance not configured")
        try:
            return aas_governance.submit(change)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/v1/changes")
    def submit(change: ChangeRequest):
        if aas_governance is not None:
            raise HTTPException(status_code=409, detail="Direct RDF writes disabled in native AAS mode")
        try:
            additions = {t.rdf() for t in change.additions}
            deletions = {t.rdf() for t in change.deletions}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if additions & deletions or not (additions or deletions):
            raise HTTPException(status_code=422, detail="Empty or conflicting change set")
        current, version = manager.store.snapshot()
        if version != change.expected_version:
            raise HTTPException(status_code=409, detail="Stale snapshot version")
        if any(t not in current for t in deletions):
            raise HTTPException(status_code=409, detail="Deletion does not exist")
        candidate = Graph()
        candidate += current
        for triple in deletions:
            candidate.remove(triple)
        for triple in additions:
            candidate.add(triple)
        flags = evidence_provider(current, candidate) if evidence_provider else {}
        result = manager.submit(candidate, expected_version=version, **flags)
        decision = ("ACCEPTED" if result["committed"] else
                    "REJECTED" if result["verdict"] == "F" else "DEFERRED")
        return dict(result, decision=decision)

    return app
