"""DTWiSE concept-role policy.

This is a design policy, not a learned classifier. Excluded concepts remain
retrievable and resolvable and are retained for future graph planning.
"""
from urllib.parse import unquote, urlsplit

DOMAIN_EVIDENCE_EXCLUDED = frozenset({"hasAssetIdentifier"})


def local_name(uri):
    p = urlsplit(uri)
    return unquote(p.fragment or p.path.rstrip("/").rsplit("/", 1)[-1])


def concept_role(uri):
    return ("graph_linking" if local_name(uri) in DOMAIN_EVIDENCE_EXCLUDED
            else "domain_evidence_candidate")


def eligible_for_domain_evidence(uri):
    return concept_role(uri) == "domain_evidence_candidate"


def partition_retrieved_hits(hits):
    """Retain original hit objects, ranks, and order in both partitions."""
    domain_candidates, graph_linking = [], []
    for rank, hit in enumerate(hits, 1):
        record = {"rank": rank, "hit": hit}
        if hit.get("uri") and not eligible_for_domain_evidence(hit["uri"]):
            graph_linking.append(record)
        else:
            domain_candidates.append(record)
    return {"domain_candidates": domain_candidates, "graph_linking": graph_linking}
