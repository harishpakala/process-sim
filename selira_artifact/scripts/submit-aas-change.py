"""Submit an explicit native AAS request; no direct GraphDB access."""
import argparse
import json
from pathlib import Path
from selira.runtime.aas_messages import AASChangeRequest
from selira.runtime.governance_client import GovernanceClient, GovernanceTransportUncertain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8002")
    args = parser.parse_args()
    change = AASChangeRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
    try:
        result = GovernanceClient(args.url).submit(change)
    except GovernanceTransportUncertain as exc:
        print(json.dumps({"decision": "DEFERRED", "persistence": "UNCONFIRMED",
                          "message_id": change.header.message_id, "reason": str(exc)}))
        return 2
    print(result.model_dump_json(indent=2))
    return 0 if result.committed else 1


if __name__ == "__main__":
    raise SystemExit(main())
