import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';

import { AppProviders } from '@/common/providers';
import { THEME_MODE_STORAGE_KEY } from '@/common/theme';

import { ThemeModeSwitch } from './ThemeModeSwitch';

afterEach(() => {
  localStorage.clear();
  document.documentElement.className = '';
});

describe('ThemeModeSwitch', () => {
  it('follows the system until a mode is picked, and remembers the pick', async () => {
    render(
      <AppProviders>
        <ThemeModeSwitch />
      </AppProviders>,
    );
    expect(
      screen.getByRole('button', { name: 'Follow the system' }),
    ).toHaveAttribute('aria-pressed', 'true');

    await userEvent.click(screen.getByRole('button', { name: 'Dark' }));
    expect(screen.getByRole('button', { name: 'Dark' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(localStorage.getItem(THEME_MODE_STORAGE_KEY)).toBe('dark');
    expect(document.documentElement).toHaveClass('dark');
  });
});
