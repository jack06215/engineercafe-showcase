import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { themeRender } from '@/common/test-utils';
import { theme } from '@/common/theme';

describe('theme', () => {
  it("reaches Emotion's css prop through MUI's ThemeProvider", () => {
    themeRender(
      <p css={(current) => ({ color: current.palette.primary.main })}>
        themed
      </p>,
    );

    expect(screen.getByText('themed')).toHaveStyle({
      color: theme.palette.primary.main,
    });
  });
});
