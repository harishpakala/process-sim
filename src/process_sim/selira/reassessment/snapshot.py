"""SC-01 snapshot model and reference qualification semantics."""

from dataclasses import dataclass

@dataclass(frozen=True)
class Snapshot:
    revision: str
    # asset URI -> assigned product reference (candidate references excluded)
    assigned: dict[str, str]
    # catalog product URI -> asset identifier
    catalog: dict[str, str]
    complete: bool = True

def check(snapshot: Snapshot, asset: str) -> str:
    if not snapshot.complete:
        return "INDETERMINATE"
    ref = snapshot.assigned.get(asset)
    if ref is None:
        return "NOT_APPLICABLE"
    matches = [p for p, identifier in snapshot.catalog.items() if identifier == ref]
    return "VALIDATED" if len(matches) == 1 else "INVALID"

