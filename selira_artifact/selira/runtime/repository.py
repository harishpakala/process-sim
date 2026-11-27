"""Repository boundary for the RDF admission engine."""
from typing import Protocol
from rdflib import Graph


class VersionedRepository(Protocol):
    """Return detached snapshots and conditionally replace admitted RDF state.

    Implementations must preserve state on version mismatch. Successful
    commits advance the version by one. This protocol alone does not
    establish native AAS durability or distributed transaction guarantees.
    """

    def snapshot(self) -> tuple[Graph, int]:
        ...

    def compare_and_commit(self, expected_version: int,
                           graph: Graph) -> tuple[bool, int]:
        ...
