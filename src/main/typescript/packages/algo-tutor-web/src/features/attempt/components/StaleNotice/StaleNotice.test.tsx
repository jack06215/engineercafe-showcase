import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { themeRender } from '@/common/test-utils';

import { StaleNotice } from './StaleNotice';

describe('StaleNotice', () => {
  it('copies the unsaved text and offers the reload', async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, 'writeText');
    const onReload = vi.fn();
    themeRender(
      <StaleNotice unsavedText="def f(): pass" onReload={onReload} />,
    );

    await user.click(screen.getByRole('button', { name: 'Copy unsaved text' }));
    expect(writeText).toHaveBeenCalledWith('def f(): pass');
    expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument();

    await user.click(
      screen.getByRole('button', { name: 'Reload saved version' }),
    );
    expect(onReload).toHaveBeenCalledOnce();
  });
});
