import { describe, expect, it, vi } from 'vitest';

import { VersionedLane } from './lane';

type Doc = { version: number; text: string };

const deferred = <T>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

describe('VersionedLane', () => {
  it('runs operations one at a time, each on the previous result', async () => {
    const lane = new VersionedLane<Doc>({ version: 1, text: '' });
    const first = deferred<Doc>();
    const seen: number[] = [];

    const a = lane.run((current) => {
      seen.push(current.version);
      return first.promise;
    });
    const b = lane.run(async (current) => {
      seen.push(current.version);
      return { version: current.version + 1, text: 'b' };
    });

    await Promise.resolve();
    expect(seen).toEqual([1]);

    first.resolve({ version: 2, text: 'a' });
    await expect(a).resolves.toEqual({ version: 2, text: 'a' });
    await expect(b).resolves.toEqual({ version: 3, text: 'b' });
    expect(seen).toEqual([1, 2]);
    expect(lane.record).toEqual({ version: 3, text: 'b' });
  });

  it('freezes on the first error until cleared or replaced', async () => {
    const lane = new VersionedLane<Doc>({ version: 1, text: '' });
    const stale = new Error('stale');

    await expect(lane.run(() => Promise.reject(stale))).rejects.toBe(stale);
    const skipped = vi.fn(async (d: Doc) => d);
    await expect(lane.run(skipped)).rejects.toBe(stale);
    expect(skipped).not.toHaveBeenCalled();
    expect(lane.error).toBe(stale);

    lane.replace({ version: 7, text: 'saved' });
    expect(lane.error).toBeNull();
    await expect(
      lane.run(async (d) => ({ ...d, version: d.version + 1 })),
    ).resolves.toEqual({ version: 8, text: 'saved' });

    await expect(lane.run(() => Promise.reject(stale))).rejects.toBe(stale);
    lane.clearError();
    expect(lane.error).toBeNull();
    expect(lane.record.version).toBe(8);
  });

  it('notifies subscribers with a new snapshot on every change', async () => {
    const lane = new VersionedLane<Doc>({ version: 1, text: '' });
    const listener = vi.fn();
    const unsubscribe = lane.subscribe(listener);
    const before = lane.getSnapshot();

    await lane.run(async () => ({ version: 2, text: 'x' }));
    expect(listener).toHaveBeenCalledTimes(1);
    expect(lane.getSnapshot()).not.toBe(before);

    unsubscribe();
    lane.replace({ version: 3, text: 'y' });
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

describe('runSoft', () => {
  it('passes soft failures to the caller without freezing the lane', async () => {
    const { runSoft } = await import('./lane');
    const lane = new VersionedLane<Doc>({ version: 1, text: '' });
    const badPath = new Error('bad path');

    await expect(
      runSoft(
        lane,
        () => Promise.reject(badPath),
        (e) => e === badPath,
      ),
    ).rejects.toBe(badPath);
    expect(lane.error).toBeNull();

    const hard = new Error('stale');
    await expect(
      runSoft(
        lane,
        () => Promise.reject(hard),
        (e) => e === badPath,
      ),
    ).rejects.toBe(hard);
    expect(lane.error).toBe(hard);
  });
});
