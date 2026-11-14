import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useBeforeUnloadGuard } from './useBeforeUnloadGuard';

const unload = () => {
  const event = new Event('beforeunload', { cancelable: true });
  window.dispatchEvent(event);
  return event;
};

describe('useBeforeUnloadGuard', () => {
  it('blocks leaving only while there are unsaved changes', () => {
    const hook = renderHook(({ when }) => useBeforeUnloadGuard(when), {
      initialProps: { when: false },
    });
    expect(unload().defaultPrevented).toBe(false);

    hook.rerender({ when: true });
    expect(unload().defaultPrevented).toBe(true);

    hook.rerender({ when: false });
    expect(unload().defaultPrevented).toBe(false);

    hook.rerender({ when: true });
    hook.unmount();
    expect(unload().defaultPrevented).toBe(false);
  });
});
