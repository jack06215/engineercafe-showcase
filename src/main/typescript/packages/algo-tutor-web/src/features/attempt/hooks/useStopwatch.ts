import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';

import type { Versioned, VersionedLane } from '../common/lane';

// SPEC §6.3: the page sends a heartbeat every 30 s while it's open.
export const HEARTBEAT_MS = 30_000;
// Active time is capped at 7 days.
export const MAX_ACTIVE_SECONDS = 7 * 24 * 60 * 60;

export type TimerAction = 'heartbeat' | 'pause' | 'resume';

// The stopwatch fields of an attempt, as the server last reported them.
export type TimerState = {
  status: 'active' | 'paused' | 'completed';
  // Counted so far, up to `lastHeartbeatAt`.
  activeSeconds: number;
  lastHeartbeatAt: string | null;
  // The server's clock when it wrote this copy, so a skewed client clock
  // doesn't skew the display.
  serverNow: string;
  // Paused by a gap of over 120 s: Resume must say whether to count it.
  needsGapDecision: boolean;
  gapSeconds: number;
};

const seconds = (from: string | null, to: string): number =>
  from === null ? 0 : Math.max(0, (Date.parse(to) - Date.parse(from)) / 1000);

// Active seconds at the server's `serverNow`: the counted time plus, while
// running, the time since the last heartbeat (which the next one counts).
export const activeSecondsAt = (timer: TimerState): number => {
  const running = timer.status === 'active' && !timer.needsGapDecision;
  const sinceHeartbeat = running
    ? seconds(timer.lastHeartbeatAt, timer.serverNow)
    : 0;
  return Math.min(
    MAX_ACTIVE_SECONDS,
    Math.floor(timer.activeSeconds + sinceHeartbeat),
  );
};

type Options<R extends Versioned> = {
  lane: VersionedLane<R>;
  timerOf: (record: R) => TimerState;
  // POST the timer action with `record.version`; resolve to the new copy.
  send: (record: R, action: TimerAction, includeGap?: boolean) => Promise<R>;
  heartbeatMs?: number;
  tickMs?: number;
};

// The attempt page's stopwatch (SPEC §6.3). The server keeps the time; this
// shows it ticking between server copies and keeps the server informed:
// a heartbeat on open, every `heartbeatMs` while running, and whenever the
// tab becomes visible again. Browsers slow timers in background tabs, but
// not below once a minute, inside the server's 120 s gap allowance.
//
// Writes go through the attempt's lane, since each bumps its version.
export const useStopwatch = <R extends Versioned>({
  lane,
  timerOf,
  send,
  heartbeatMs = HEARTBEAT_MS,
  tickMs = 1000,
}: Options<R>) => {
  const { record } = useSyncExternalStore(
    lane.subscribe,
    lane.getSnapshot,
    lane.getSnapshot,
  );
  const timer = timerOf(record);
  const running = timer.status === 'active' && !timer.needsGapDecision;
  const base = activeSecondsAt(timer);

  // Local ticks since this server copy arrived, tagged with the copy they
  // belong to so a new copy starts again from zero.
  const [tick, setTick] = useState({ copy: timer.serverNow, elapsedMs: 0 });
  useEffect(() => {
    if (!running) return;
    const start = Date.now();
    const id = window.setInterval(() => {
      setTick({ copy: timer.serverNow, elapsedMs: Date.now() - start });
    }, tickMs);
    return () => window.clearInterval(id);
  }, [running, timer.serverNow, tickMs]);
  const extra =
    running && tick.copy === timer.serverNow
      ? Math.floor(tick.elapsedMs / 1000)
      : 0;

  // Callers may pass fresh functions each render; the timers below must not
  // restart (and re-send a heartbeat) because of that.
  const latestRef = useRef({ timerOf, send });
  useEffect(() => {
    latestRef.current = { timerOf, send };
  });

  const act = useCallback(
    (action: TimerAction, includeGap?: boolean) =>
      lane.run((record) => latestRef.current.send(record, action, includeGap)),
    [lane],
  );

  const heartbeat = useCallback(async () => {
    // A frozen lane (an error showing) or a stopped watch sends nothing.
    if (lane.error) return;
    if (latestRef.current.timerOf(lane.record).status !== 'active') return;
    await act('heartbeat').catch(() => undefined);
  }, [lane, act]);

  const open = timer.status !== 'completed';
  useEffect(() => {
    if (!open) return;
    void heartbeat();
    const id = window.setInterval(() => void heartbeat(), heartbeatMs);
    const onVisible = () => {
      if (document.visibilityState === 'visible') void heartbeat();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [open, heartbeat, heartbeatMs]);

  return {
    seconds: Math.min(MAX_ACTIVE_SECONDS, base + extra),
    running,
    paused: timer.status === 'paused',
    // "Count this gap?" is pending; Resume needs an answer.
    gapPending: timer.needsGapDecision,
    gapSeconds: timer.gapSeconds,
    pause: () => act('pause'),
    resume: (includeGap?: boolean) => act('resume', includeGap),
  };
};
