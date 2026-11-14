import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { VersionedLane } from '../common/lane';

import {
  activeSecondsAt,
  type TimerAction,
  type TimerState,
  useStopwatch,
} from './useStopwatch';

type Attempt = { version: number; timer: TimerState };

const T0 = Date.parse('2026-11-08T09:00:00Z');
const iso = (ms: number) => new Date(ms).toISOString();

const running = (activeSeconds: number, sinceHeartbeat = 0): TimerState => ({
  status: 'active',
  activeSeconds,
  lastHeartbeatAt: iso(T0 - sinceHeartbeat * 1000),
  serverNow: iso(T0),
  needsGapDecision: false,
  gapSeconds: 0,
});

// A fake server that counts heartbeats on its own clock, as SPEC §6.3 does.
const makeServer = () => {
  const calls: { action: TimerAction; includeGap?: boolean }[] = [];
  const send = vi.fn(
    async (a: Attempt, action: TimerAction, includeGap?: boolean) => {
      calls.push({ action, includeGap });
      const now = Date.now();
      const t = a.timer;
      const gap = t.lastHeartbeatAt
        ? (now - Date.parse(t.lastHeartbeatAt)) / 1000
        : 0;
      let timer: TimerState = { ...t, serverNow: iso(now) };
      if (action === 'heartbeat' && t.status === 'active') {
        timer =
          gap > 120
            ? {
                ...timer,
                status: 'paused',
                needsGapDecision: true,
                gapSeconds: Math.round(gap),
              }
            : {
                ...timer,
                activeSeconds: t.activeSeconds + Math.round(gap),
                lastHeartbeatAt: iso(now),
              };
      } else if (action === 'pause') {
        timer = {
          ...timer,
          status: 'paused',
          activeSeconds: t.activeSeconds + Math.round(gap),
          lastHeartbeatAt: iso(now),
        };
      } else if (action === 'resume') {
        timer = {
          ...timer,
          status: 'active',
          needsGapDecision: false,
          activeSeconds:
            t.activeSeconds + (includeGap ? Math.max(t.gapSeconds, gap) : 0),
          lastHeartbeatAt: iso(now),
        };
      }
      return { version: a.version + 1, timer };
    },
  );
  return { send, calls };
};

const setup = (timer: TimerState) => {
  const server = makeServer();
  const lane = new VersionedLane<Attempt>({ version: 1, timer });
  const hook = renderHook(() =>
    useStopwatch({ lane, timerOf: (a) => a.timer, send: server.send }),
  );
  return { server, lane, hook };
};

const advance = async (ms: number) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};

beforeEach(() => {
  vi.useFakeTimers({ now: T0 });
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => 'visible',
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('activeSecondsAt', () => {
  it('adds the time since the last heartbeat while running', () => {
    expect(activeSecondsAt(running(100, 5))).toBe(105);
  });

  it('counts nothing more while paused or waiting on the gap question', () => {
    expect(activeSecondsAt({ ...running(100, 5), status: 'paused' })).toBe(100);
    expect(
      activeSecondsAt({ ...running(100, 5), needsGapDecision: true }),
    ).toBe(100);
  });

  it('caps at 7 days', () => {
    expect(activeSecondsAt(running(7 * 24 * 3600, 60))).toBe(7 * 24 * 3600);
  });
});

describe('useStopwatch', () => {
  it('sends a heartbeat on open and every 30 s, and ticks in between', async () => {
    const { server, hook } = setup(running(100, 5));
    await advance(0);
    expect(server.calls).toEqual([
      { action: 'heartbeat', includeGap: undefined },
    ]);
    expect(hook.result.current.seconds).toBe(105);

    await advance(3000);
    expect(hook.result.current.seconds).toBe(108);

    await advance(27_000);
    expect(server.calls).toHaveLength(2);
    expect(hook.result.current.seconds).toBe(135);
    expect(hook.result.current.running).toBe(true);
  });

  it('stops ticking and heartbeating while paused, then resumes', async () => {
    const { server, hook } = setup(running(60));
    await advance(10_000);
    await act(async () => {
      await hook.result.current.pause();
    });
    expect(hook.result.current.paused).toBe(true);
    const shown = hook.result.current.seconds;
    expect(shown).toBe(70);

    await advance(120_000);
    expect(hook.result.current.seconds).toBe(shown);
    expect(server.calls.filter((c) => c.action === 'heartbeat')).toHaveLength(
      1,
    );

    await act(async () => {
      await hook.result.current.resume();
    });
    await advance(5000);
    expect(hook.result.current.seconds).toBe(75);
  });

  it('asks about a gap after the laptop slept, and counts it on yes', async () => {
    const { server, hook } = setup(running(200));
    await advance(0);

    // Asleep: no timers fire, then the tab wakes 10 minutes later.
    vi.setSystemTime(T0 + 600_000);
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(hook.result.current.gapPending).toBe(true);
    expect(hook.result.current.running).toBe(false);
    expect(hook.result.current.gapSeconds).toBe(600);
    expect(hook.result.current.seconds).toBe(200);

    await act(async () => {
      await hook.result.current.resume(true);
    });
    expect(server.calls.at(-1)).toEqual({ action: 'resume', includeGap: true });
    expect(hook.result.current.gapPending).toBe(false);
    expect(hook.result.current.seconds).toBe(800);
  });

  it('does nothing for a completed attempt', async () => {
    const { server, hook } = setup({ ...running(300), status: 'completed' });
    await advance(60_000);
    expect(server.send).not.toHaveBeenCalled();
    expect(hook.result.current.seconds).toBe(300);
  });
});
