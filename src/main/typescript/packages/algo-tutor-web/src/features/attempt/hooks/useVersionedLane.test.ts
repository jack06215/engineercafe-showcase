import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useVersionedLane } from './useVersionedLane';

describe('useVersionedLane', () => {
  it('re-renders with what the lane commits', async () => {
    const hook = renderHook(() => useVersionedLane({ version: 1, text: 'a' }));
    const { lane } = hook.result.current;

    await act(async () => {
      await lane.run(async (r) => ({ ...r, version: 2, text: 'b' }));
    });
    expect(hook.result.current.record).toEqual({ version: 2, text: 'b' });
    expect(hook.result.current.lane).toBe(lane);

    const boom = new Error('boom');
    await act(async () => {
      await lane.run(() => Promise.reject(boom)).catch(() => undefined);
    });
    expect(hook.result.current.error).toBe(boom);
  });
});
