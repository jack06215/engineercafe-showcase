import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from packages.algo_tutor.domain.enums import AttemptStatus, TimerAction
from packages.algo_tutor.domain.timer import (
    AttemptCompleted,
    GapDecisionRequired,
    TimerState,
    apply_timer,
    current_seconds,
    format_mmss,
    parse_mmss,
)

T0 = datetime(2026, 11, 8, 9, tzinfo=UTC)
HB, PAUSE, RESUME = TimerAction.HEARTBEAT, TimerAction.PAUSE, TimerAction.RESUME


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


class StopwatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.s = TimerState.started(T0)

    def test_heartbeats_within_120_s_count(self) -> None:
        s = apply_timer(self.s, HB, at(30))
        s = apply_timer(s, HB, at(150))  # exactly 120 s later still counts
        self.assertEqual(
            (s.status, s.active_seconds, s.last_heartbeat_at),
            (AttemptStatus.ACTIVE, 150, at(150)),
        )

    def test_a_longer_gap_pauses_and_is_not_counted(self) -> None:
        s = apply_timer(self.s, HB, at(30))
        s = apply_timer(s, HB, at(30 + 121))
        self.assertEqual(s.status, AttemptStatus.PAUSED)
        self.assertTrue(s.needs_gap_decision)
        self.assertEqual(
            (s.gap_seconds, s.active_seconds, s.running_since), (121, 30, None)
        )
        self.assertEqual(s.last_heartbeat_at, at(30))
        # Further heartbeats while paused change nothing.
        self.assertEqual(apply_timer(s, HB, at(500)), s)

    def test_resume_after_a_gap_needs_an_answer(self) -> None:
        s = apply_timer(apply_timer(self.s, HB, at(30)), HB, at(1000))
        with self.assertRaises(GapDecisionRequired):
            apply_timer(s, RESUME, at(1010))
        no = apply_timer(s, RESUME, at(1010), include_gap=False)
        self.assertEqual(
            (no.status, no.active_seconds, no.needs_gap_decision, no.gap_seconds),
            (AttemptStatus.ACTIVE, 30, False, 0),
        )
        self.assertEqual((no.running_since, no.last_heartbeat_at), (at(1010), at(1010)))
        # Yes adds max(gap, now − last heartbeat): 1010 − 30 = 980 > the 970 s gap.
        yes = apply_timer(s, RESUME, at(1010), include_gap=True)
        self.assertEqual(yes.active_seconds, 30 + 980)

    def test_resume_detects_a_gap_itself(self) -> None:
        # The tab slept and the first request is the resume: the gap is detected first.
        with self.assertRaises(GapDecisionRequired):
            apply_timer(self.s, RESUME, at(600))
        s = apply_timer(self.s, RESUME, at(600), include_gap=True)
        self.assertEqual(s.active_seconds, 600)

    def test_pause_and_resume_without_a_gap(self) -> None:
        s = apply_timer(self.s, PAUSE, at(60))
        self.assertEqual(
            (s.status, s.active_seconds, s.running_since),
            (AttemptStatus.PAUSED, 60, None),
        )
        s = apply_timer(s, RESUME, at(3600))  # paused time is never counted
        self.assertEqual((s.status, s.active_seconds), (AttemptStatus.ACTIVE, 60))
        s = apply_timer(s, HB, at(3630))
        self.assertEqual(s.active_seconds, 90)

    def test_capped_at_seven_days(self) -> None:
        s = replace(self.s, active_seconds=604_790)
        self.assertEqual(apply_timer(s, HB, at(100)).active_seconds, 604_800)

    def test_completed_attempts_refuse(self) -> None:
        with self.assertRaises(AttemptCompleted):
            apply_timer(replace(self.s, status=AttemptStatus.COMPLETED), HB, at(1))

    def test_current_seconds(self) -> None:
        s = apply_timer(self.s, HB, at(30))
        self.assertEqual(current_seconds(s, at(90)), 90)
        self.assertEqual(
            current_seconds(s, at(500)), 30
        )  # a pending gap isn't shown as time
        self.assertEqual(current_seconds(apply_timer(s, PAUSE, at(40)), at(500)), 40)


class MmSsTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        self.assertEqual(format_mmss(0), "0:00")
        self.assertEqual(format_mmss(25 * 60 + 7), "25:07")
        self.assertEqual(parse_mmss("25:07"), 1507)
        self.assertEqual(parse_mmss("9999:59"), 9999 * 60 + 59)

    def test_bad_times(self) -> None:
        for bad in ("", "1:7", "1:60", "12345:00", ":30", "a:00", "1:00:00"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_mmss(bad)


if __name__ == "__main__":
    unittest.main()
