"""Client for participating applications; never falls back to direct RDF writes."""
import requests
from .aas_messages import AASChangeRequest, AASChangeResponse


class GovernanceTransportUncertain(RuntimeError):
    """No confirmed response; preserve original request identity and payload."""


class GovernanceClient:
    def __init__(self, base_url="http://127.0.0.1:8002", *, timeout=180, session=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session if session is not None else requests.Session()

    def health(self):
        response = self.session.get(self.base_url + "/api/v1/health", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def submit(self, change: AASChangeRequest) -> AASChangeResponse:
        if not isinstance(change, AASChangeRequest):
            raise TypeError("Expected AASChangeRequest")
        try:
            response = self.session.post(self.base_url + "/api/v1/changes/aas",
                json=change.model_dump(mode="json"), timeout=self.timeout)
            if response.status_code >= 500:
                raise GovernanceTransportUncertain("Server outcome unconfirmed")
            response.raise_for_status()
            result = AASChangeResponse.model_validate(response.json())
            if result.message_id != change.header.message_id:
                raise GovernanceTransportUncertain("Response identity mismatch")
            return result
        except requests.HTTPError:
            raise
        except (requests.RequestException, ValueError) as exc:
            raise GovernanceTransportUncertain("No confirmed governance response") from exc
