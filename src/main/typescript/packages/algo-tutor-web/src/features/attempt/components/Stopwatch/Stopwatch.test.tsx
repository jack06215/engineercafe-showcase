import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { themeRender } from '@/common/test-utils';

import { Stopwatch } from './Stopwatch';

const props = {
  seconds: 754,
  running: true,
  paused: false,
  gapPending: false,
  gapSeconds: 0,
  onPause: vi.fn(),
  onResume: vi.fn(),
};

describe('Stopwatch', () => {
  it('shows the time as mm:ss with Pause while running', async () => {
    const onPause = vi.fn();
    themeRender(<Stopwatch {...props} onPause={onPause} />);
    expect(screen.getByLabelText('Active time')).toHaveTextContent('12:34');
    await userEvent.click(screen.getByRole('button', { name: 'Pause' }));
    expect(onPause).toHaveBeenCalledOnce();
  });

  it('shows the Paused banner and Resume', async () => {
    const onResume = vi.fn();
    themeRender(
      <Stopwatch {...props} running={false} paused onResume={onResume} />,
    );
    expect(screen.getByText('Paused')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Resume' }));
    expect(onResume).toHaveBeenCalledWith();
  });

  it('asks whether to count a gap', async () => {
    const onResume = vi.fn();
    themeRender(
      <Stopwatch
        {...props}
        running={false}
        paused
        gapPending
        gapSeconds={600}
        onResume={onResume}
      />,
    );
    expect(screen.getByText(/went quiet for 10:00/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Resume' })).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: 'Count it' }));
    expect(onResume).toHaveBeenLastCalledWith(true);
    await userEvent.click(
      screen.getByRole('button', { name: "Don't count it" }),
    );
    expect(onResume).toHaveBeenLastCalledWith(false);
  });
});
