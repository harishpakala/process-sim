"""Deterministic Phase 5.1 domain resolution from explicit question mentions."""
import re

from process_sim.dtwise.experimental_shacl_subgraph import SH_NODE_SHAPE


class DomainResolutionError(ValueError):
    """Domain is missing, ambiguous, or conflicts with the explicit override."""


def resolve_domain(question, available_domains, override=None, *, schema=None):
    """Return a unique indexed domain; never silently select a default.

    Matches complete domain identifiers, case-insensitively. This initial
    version does not infer domains from schema property names or an LLM.
    """
    domains = sorted({d.casefold() for d in available_domains if isinstance(d, str) and d})
    if not domains:
        raise DomainResolutionError("No schema domains available")
    mentioned = [d for d in domains if re.search(
        r"(?<![A-Za-z0-9_])" + re.escape(d) + r"(?![A-Za-z0-9_])",
        question, re.IGNORECASE)]
    if len(mentioned) > 1:
        raise DomainResolutionError("Ambiguous domain references: " + ", ".join(mentioned))
    if override is not None:
        selected = override.casefold()
        if selected not in domains:
            raise DomainResolutionError("Unknown schema domain: " + override)
        if mentioned and mentioned[0] != selected:
            raise DomainResolutionError(
                f"Question domain {mentioned[0]} conflicts with --domain {selected}")
        return selected
    if not mentioned:
        if schema is not None:
            return infer_domain_from_shapes(question, domains, schema)
        raise DomainResolutionError(
            "Domain unresolved: mention an indexed domain in the question or use --domain")
    return mentioned[0]


def infer_domain_from_shapes(question, domains, schema):
    """Infer only when indexed NodeShape labels support exactly one domain.

    Property names alone (e.g. Address) are too generic to route safely.
    """
    labels = {}
    for concept in schema.get("concepts", []):
        domain = concept.get("domain", "").casefold()
        if domain not in domains or SH_NODE_SHAPE not in concept.get("types", []):
            continue
        for label in concept.get("labels", []):
            if not isinstance(label, str) or not label.strip() or "shacl shape" in label.casefold():
                continue
            labels.setdefault(label.casefold(), set()).add(domain)
    hits = set()
    for label, owners in labels.items():
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(label) + r"(?![A-Za-z0-9_])",
                     question, re.IGNORECASE):
            hits.update(owners)
    if len(hits) > 1:
        raise DomainResolutionError("Ambiguous schema-domain evidence: " + ", ".join(sorted(hits)))
    if not hits:
        raise DomainResolutionError(
            "Domain unresolved: no indexed NodeShape evidence; use --domain")
    return next(iter(hits))
