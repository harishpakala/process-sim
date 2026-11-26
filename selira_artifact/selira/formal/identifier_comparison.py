"""Explicit comparison policy for authoritative asset identifiers."""

import re
from urllib.parse import urlsplit


def normalized_tag(value: str) -> str:
    """Ignore only underscore and hyphen separators; preserve case."""
    return re.sub(r"[_-]", "", value)


def asset_suffix(identifier: str) -> str:
    """Extract the final path segment of an absolute HTTP(S) identifier."""
    parts = urlsplit(identifier)
    if (parts.scheme not in ("http", "https") or not parts.netloc
            or parts.query or parts.fragment):
        raise ValueError("Expected an absolute asset identifier without query or fragment")
    suffix = parts.path.rsplit("/", 1)[-1]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", suffix):
        raise ValueError("Unsupported asset identifier suffix")
    return suffix


def identifier_matches(local_id: str, asset_identifier: str, *, exceptions=()) -> bool:
    """Compare a local tag with the authoritative URI or an explicit approved pair."""
    suffix = asset_suffix(asset_identifier)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", local_id):
        raise ValueError("Unsupported local identifier")
    local = normalized_tag(local_id)
    authoritative = normalized_tag(suffix)
    if not local or not authoritative:
        raise ValueError("Empty normalized identifier")
    return local == authoritative or (local_id, asset_identifier) in exceptions
