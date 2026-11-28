"""Transport models for proposed native AAS changes.

Envelope validation is not AAS metamodel validation, semantic resolution,
authorization, or evidence qualification.
"""
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class Header(StrictModel):
    message_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    message_type: Literal["InformationChangeProposed"] = "InformationChangeProposed"


class Domain(StrictModel):
    name: str = Field(min_length=1)
    submodel_id: str = Field(min_length=1)
    semantic_id: str | None = Field(default=None, min_length=1)


class PolicyIntent(StrictModel):
    policy_id: str = Field(min_length=1)
    activation_terminal: str | None = Field(default=None, min_length=1)


class Operation(StrictModel):
    type: Literal["CREATE", "UPDATE", "DELETE"]
    id_short_path: str = Field(min_length=1)
    expected_version: int = Field(ge=0)


class AASChangeRequest(StrictModel):
    header: Header
    domain: Domain
    operation: Operation
    policy: PolicyIntent | None = None
    payload: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_payload(self):
        if self.operation.type == "DELETE":
            if self.payload is not None:
                raise ValueError("DELETE must not contain a replacement payload")
        else:
            if not self.payload:
                raise ValueError("CREATE and UPDATE require a native AAS element")
            model_type = self.payload.get("modelType")
            if not isinstance(model_type, str) or not model_type.strip():
                raise ValueError("AAS element requires modelType")
        return self


class ContractOutcome(StrictModel):
    contract_id: str = Field(min_length=1)
    verdict: Literal["V", "F", "U", "NA"]


class AASChangeResponse(StrictModel):
    message_id: str = Field(min_length=1)
    message_type: Literal["InformationChangeResponse"] = "InformationChangeResponse"
    decision: Literal["ACCEPTED", "REJECTED", "DEFERRED"]
    triggered_policies: list[str] = Field(default_factory=list)
    evaluated_contracts: list[ContractOutcome] = Field(default_factory=list)
    committed: bool
    repository_version: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_decision(self):
        if self.committed != (self.decision == "ACCEPTED"):
            raise ValueError("Only accepted changes may be committed")
        return self
