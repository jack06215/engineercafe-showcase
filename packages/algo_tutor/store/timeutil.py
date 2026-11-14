"""How times and dates are written to the database (SPEC.md §16).

Timestamps are ISO-8601 UTC in one fixed shape, so they also sort as text:
`2026-11-08T07:53:05.872000Z`. Dates are `YYYY-MM-DD` in the learner's
timezone.
"""

import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def new_id() -> str:
    return str(uuid.uuid4())


def iso_utc(moment: datetime) -> str:
    """`moment` as stored. Naive datetimes are rejected rather than guessed."""
    if moment.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_iso(text: str) -> datetime:
    """A stored timestamp back as an aware UTC datetime."""
    return datetime.fromisoformat(text).astimezone(UTC)


def now_utc() -> datetime:
    return datetime.now(UTC)


def local_date(moment: datetime, timezone: str) -> date:
    """The calendar date of `moment` in `timezone` (an IANA name)."""
    return moment.astimezone(ZoneInfo(timezone)).date()
