"""Timestamps: ISO-8601 UTC with milliseconds and a ``Z`` suffix (R7).

Example: ``2026-10-18T14:03:12.500Z``. The database stores the same format,
so stored timestamps sort lexicographically in time order.
"""

from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_iso(dt: datetime) -> str:
    """Format an aware datetime as ``YYYY-MM-DDTHH:MM:SS.mmmZ`` in UTC."""
    if dt.tzinfo is None:
        raise ValueError("to_iso requires a timezone-aware datetime")
    utc = dt.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def utc_now_iso() -> str:
    return to_iso(utc_now())


def parse_iso(value: str) -> datetime:
    """Parse a timestamp produced by :func:`to_iso` back into an aware UTC datetime."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
