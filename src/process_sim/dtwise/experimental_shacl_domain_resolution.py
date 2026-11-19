"""Deterministic Phase 5.1 domain resolution from explicit question mentions."""
import re


class DomainResolutionError(ValueError):
    """Domain is missing, ambiguous, or conflicts with the explicit override."""


def resolve_domain(question, available_domains, override=None):
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
        raise DomainResolutionError(
            "Domain unresolved: mention an indexed domain in the question or use --domain")
    return mentioned[0]
