"""Dedupe normalized RFPs against what's already in Postgres.

Strategy: exact ``dedupe_hash`` match is authoritative. Near-match
(title similarity) is a stretch goal from the supplemental plan
amendment 2.G and isn't implemented for POC — it would only pay off
when the same RFP flows through multiple adapters, which doesn't
happen at demo scale.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from ...db.client import upsert_rfp
from ...models.rfp import RFP

log = logging.getLogger(__name__)


def dedupe_and_upsert(rfp: RFP) -> Tuple[RFP, bool]:
    """Persist ``rfp`` if new, return the canonical row otherwise.

    Returns
    -------
    (persisted_rfp, was_new)
        ``was_new`` is True if this call inserted a new row; False if the
        ``dedupe_hash`` already matched an existing row (in which case
        ``persisted_rfp`` is the existing row, not the input).
    """
    before_id = rfp.id
    stored = upsert_rfp(rfp)
    return stored, stored.id == before_id
