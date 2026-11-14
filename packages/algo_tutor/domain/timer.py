"""The server-kept stopwatch (SPEC §6.3).

Ported from BloomCode's `/timer` endpoint (`attempts/attempts.ts`), which its
web UI never called; algo_tutor's attempt page sends a heartbeat every 30 s.
"""

import math
from dataclasses import dataclass, replace
from datetime import datetime

from packages.algo_tutor.domain.constants import (
    HEARTBEAT_GAP_SECONDS,
    MAX_ACTIVE_SECONDS,
)
from packages.algo_tutor.domain.enums import AttemptStatus, TimerAction


class GapDecisionRequired(ValueError):
    """Resume after a gap without answering "count this gap?" (409 GAP_DECISION)."""


class AttemptCompleted(ValueError):
    """Timer action on a completed attempt (409 COMPLETED)."""


@dataclass(frozen=True)
class TimerState:
    status: AttemptStatus
    active_seconds: int
    gap_seconds: int
    running_since: datetime | None
    last_heartbeat_at: datetime | None
    needs_gap_decision: bool

    @classmethod
    def started(cls, now: datetime) -> "TimerState":
        """A new attempt: running from `now`."""
        return cls(AttemptStatus.ACTIVE, 0, 0, now, now, False)


def _seconds_since(then: datetime, now: datetime) -> int:
    return max(0, math.floor((now - then).total_seconds()))


def _cap(seconds: int) -> int:
    return min(MAX_ACTIVE_SECONDS, seconds)


def apply_timer(
    state: TimerState,
    action: TimerAction,
    now: datetime,
    include_gap: bool | None = None,
) -> TimerState:
    """One `heartbeat`, `pause` or `resume`.

    While active, the time since the last heartbeat is counted if it is at
    most 120 s. A longer gap (the laptop slept, the tab was closed) pauses
    the attempt with "count this gap?" pending and doesn't count it. Resuming
    then needs `include_gap`; yes adds max(gap, now − last heartbeat).
    Active time is capped at 7 days.
    """
    if state.status is AttemptStatus.COMPLETED:
        raise AttemptCompleted("Attempt already completed")
    s = state
    if s.status is AttemptStatus.ACTIVE and s.last_heartbeat_at is not None:
        delta = _seconds_since(s.last_heartbeat_at, now)
        if delta > HEARTBEAT_GAP_SECONDS:
            s = replace(
                s,
                status=AttemptStatus.PAUSED,
                running_since=None,
                needs_gap_decision=True,
                gap_seconds=delta,
            )
        else:
            s = replace(
                s, active_seconds=_cap(s.active_seconds + delta), last_heartbeat_at=now
            )

    if action is TimerAction.RESUME:
        active = s.active_seconds
        if s.needs_gap_decision:
            if include_gap is None:
                raise GapDecisionRequired(
                    "Choose whether to include the disconnected interval"
                )
            if include_gap:
                since = (
                    _seconds_since(s.last_heartbeat_at, now)
                    if s.last_heartbeat_at
                    else 0
                )
                active = _cap(active + max(s.gap_seconds, since))
        s = replace(
            s,
            status=AttemptStatus.ACTIVE,
            active_seconds=active,
            needs_gap_decision=False,
            gap_seconds=0,
            running_since=now,
            last_heartbeat_at=now,
        )
    elif action is TimerAction.PAUSE:
        s = replace(s, status=AttemptStatus.PAUSED, running_since=None)
    return s


def current_seconds(state: TimerState, now: datetime) -> int:
    """Active time as of `now`, for display and the finish form's default.

    Counts the running stretch since the last heartbeat only while it would
    still count (≤ 120 s); a longer one is the pending gap.
    """
    if state.status is AttemptStatus.ACTIVE and state.last_heartbeat_at is not None:
        delta = _seconds_since(state.last_heartbeat_at, now)
        if delta <= HEARTBEAT_GAP_SECONDS:
            return _cap(state.active_seconds + delta)
    return state.active_seconds


def format_mmss(seconds: int) -> str:
    """The finish form's time field (`^[0-9]{1,4}:[0-5][0-9]$`)."""
    minutes, secs = divmod(max(0, seconds), 60)
    return f"{min(minutes, 9999)}:{secs:02d}"


def parse_mmss(text: str) -> int:
    """Seconds from `mm:ss` as the finish form sends it."""
    minutes, _, secs = text.partition(":")
    if not (
        minutes.isdigit()
        and 1 <= len(minutes) <= 4
        and len(secs) == 2
        and secs.isdigit()
        and int(secs) < 60
    ):
        raise ValueError(f"Time must be mm:ss, got {text!r}")
    return int(minutes) * 60 + int(secs)
