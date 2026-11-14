import { render } from '@testing-library/react';
import { StrictMode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { useMount } from '@/hooks/useMount';

const Probe = ({ effect }: { effect: () => void }) => {
  useMount(effect);
  return null;
};

describe('useMount', () => {
  it('runs once without StrictMode, as in production', () => {
    const effect = vi.fn();
    const { rerender } = render(<Probe effect={effect} />);
    rerender(<Probe effect={effect} />);

    expect(effect).toHaveBeenCalledOnce();
  });

  it('runs once under StrictMode, which re-runs effects in development', () => {
    const effect = vi.fn();
    const { rerender } = render(
      <StrictMode>
        <Probe effect={effect} />
      </StrictMode>,
    );
    rerender(
      <StrictMode>
        <Probe effect={effect} />
      </StrictMode>,
    );

    expect(effect).toHaveBeenCalledOnce();
  });
});
