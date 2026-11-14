import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '@/api/client';

import { VersionedLane } from '../common/lane';

import { AUTOSAVE_DELAY_MS, useAutosave } from './useAutosave';

type Attempt = { version: number; code: string; notes: string };
type Draft = { code: string; notes: string };

const draftOf = (a: Attempt): Draft => ({ code: a.code, notes: a.notes });
const sameDraft = (a: Draft, b: Draft) =>
  a.code === b.code && a.notes === b.notes;

// A fake server: applies the draft if the version matches, else 409.
const makeServer = (initial: Attempt) => {
  let saved = initial;
  const calls: { version: number; draft: Draft }[] = [];
  let gate: Promise<void> | null = null;
  const save = vi.fn(async (record: Attempt, draft: Draft) => {
    calls.push({ version: record.version, draft });
    if (gate) await gate;
    if (record.version !== saved.version) {
      throw new ApiError(409, 'STALE', 'Attempt changed elsewhere; reload it');
    }
    saved = { ...draft, version: saved.version + 1 };
    return saved;
  });
  return {
    save,
    calls,
    get saved() {
      return saved;
    },
    // Someone else wrote: the next save from us is stale.
    bumpElsewhere(code: string) {
      saved = { ...saved, code, version: saved.version + 1 };
    },
    hold() {
      let release!: () => void;
      gate = new Promise((resolve) => {
        release = () => {
          gate = null;
          resolve();
        };
      });
      return release;
    },
  };
};

const setup = (initial: Attempt = { version: 1, code: '', notes: '' }) => {
  const server = makeServer(initial);
  const lane = new VersionedLane(initial);
  const hook = renderHook(() =>
    useAutosave({ lane, draftOf, sameDraft, save: server.save }),
  );
  return { server, lane, hook };
};

const advance = async (ms: number) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useAutosave', () => {
  it('saves once, 650 ms after the last edit, with the latest text and version', async () => {
    const { server, hook } = setup();
    expect(hook.result.current.statusLabel).toBe('Saved');

    act(() => hook.result.current.setDraft((d) => ({ ...d, code: 'a' })));
    expect(hook.result.current.statusLabel).toBe('Unsaved changes');
    await advance(400);
    act(() => hook.result.current.setDraft((d) => ({ ...d, code: 'ab' })));
    await advance(AUTOSAVE_DELAY_MS - 1);
    expect(server.save).not.toHaveBeenCalled();

    await advance(1);
    expect(server.calls).toEqual([
      { version: 1, draft: { code: 'ab', notes: '' } },
    ]);
    expect(hook.result.current.statusLabel).toBe('Saved');
    expect(hook.result.current.record.version).toBe(2);
  });

  it('shows Saving… while a save runs, and queues the next behind it', async () => {
    const { server, hook } = setup();
    const release = server.hold();

    act(() => hook.result.current.setDraft({ code: 'one', notes: '' }));
    await advance(AUTOSAVE_DELAY_MS);
    expect(hook.result.current.statusLabel).toBe('Saving…');

    // Typed during the save: waits for it, then goes out with version 2.
    act(() => hook.result.current.setDraft({ code: 'two', notes: 'n' }));
    await advance(AUTOSAVE_DELAY_MS);
    expect(server.calls).toHaveLength(1);

    await act(async () => {
      release();
      await vi.runAllTimersAsync();
    });
    expect(server.calls).toEqual([
      { version: 1, draft: { code: 'one', notes: '' } },
      { version: 2, draft: { code: 'two', notes: 'n' } },
    ]);
    expect(hook.result.current.statusLabel).toBe('Saved');
  });

  it('freezes on 409 STALE, keeps the edits, and reloads the saved version', async () => {
    const { server, hook } = setup();
    server.bumpElsewhere('from another tab');

    act(() => hook.result.current.setDraft({ code: 'mine', notes: '' }));
    await advance(AUTOSAVE_DELAY_MS);
    expect(hook.result.current.statusLabel).toBe('Not saved');
    expect(hook.result.current.stale).toBe(true);
    expect(hook.result.current.draft.code).toBe('mine');

    // Frozen: further edits aren't sent.
    act(() => hook.result.current.setDraft({ code: 'mine 2', notes: '' }));
    await advance(AUTOSAVE_DELAY_MS * 3);
    expect(server.save).toHaveBeenCalledTimes(1);

    await act(async () => {
      await hook.result.current.reload(async () => server.saved);
    });
    expect(hook.result.current.stale).toBe(false);
    expect(hook.result.current.draft.code).toBe('from another tab');
    expect(hook.result.current.statusLabel).toBe('Saved');
  });

  it('retries after a network error', async () => {
    const { server, hook } = setup();
    server.save.mockRejectedValueOnce(
      new ApiError(0, 'UNREACHABLE', 'API down'),
    );

    act(() => hook.result.current.setDraft({ code: 'x', notes: '' }));
    await advance(AUTOSAVE_DELAY_MS);
    expect(hook.result.current.statusLabel).toBe('Not saved');
    expect(hook.result.current.stale).toBe(false);

    await act(async () => {
      await hook.result.current.retry();
    });
    expect(hook.result.current.statusLabel).toBe('Saved');
    expect(server.saved.code).toBe('x');
  });

  it('flush saves at once', async () => {
    const { server, hook } = setup();
    act(() => hook.result.current.setDraft({ code: 'now', notes: '' }));
    await act(async () => {
      await hook.result.current.flush();
    });
    expect(server.saved.code).toBe('now');
    expect(hook.result.current.unsaved).toBe(false);
  });

  it('saves nothing when disabled', async () => {
    const server = makeServer({ version: 1, code: '', notes: '' });
    const lane = new VersionedLane({ version: 1, code: '', notes: '' });
    const hook = renderHook(() =>
      useAutosave({
        lane,
        draftOf,
        sameDraft,
        save: server.save,
        enabled: false,
      }),
    );
    act(() => hook.result.current.setDraft({ code: 'x', notes: '' }));
    await advance(AUTOSAVE_DELAY_MS * 2);
    expect(server.save).not.toHaveBeenCalled();
  });
});
