"""Guarded historical-data consumer; authorization precedes temporal retrieval.

This is an experimental SELiRA path, not a replacement for asset_history.
Reviewed declarations are assertions, not independently authenticated evidence.
"""

# Created: 2026-10-29
# Author: Harish
from __future__ import annotations

from uuid import UUID

from .consumer_policy import authorize_use
from .graphdb import resolve_graphdb_correspondence


def guarded_asset_history(asset_iri, requested_property, run_id, *, limit=1000,
                          declarations=(), correspondence_reader=None,
                          samples_reader=None, endpoint=None):
    """Retrieve samples only after correspondence authorization succeeds."""
    uid = str(UUID(str(run_id)))
    if type(limit) is not int or not 1 <= limit <= 5000:
        raise ValueError("Limit must be 1..5000")
    if correspondence_reader is None:
        correspondence_reader = resolve_graphdb_correspondence
    result = correspondence_reader(
        asset_iri, requested_property, declarations=declarations, endpoint=endpoint
    )
    response = {
        "assetIri": asset_iri,
        "requestedProperty": requested_property,
        "runId": uid,
        "resolution": result.to_dict(),
        "authorized": authorize_use(result),
        "points": [],
    }
    if not response["authorized"]:
        return response
    if samples_reader is None:
        from process_sim.api.timeseries import query_samples
        samples_reader = query_samples
    samples = samples_reader(uid, result.selected_signal, limit)
    response["points"] = [
        {"time": t, "value": value, "observedAt": stamp.isoformat()}
        for t, value, stamp in samples
    ]
    response["signal"] = result.selected_signal
    return response
