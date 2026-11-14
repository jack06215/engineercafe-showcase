import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { problemRow, topicLevels } from '@/api/fixtures';
import { apiErrorResponse, fakeApi, routeRender } from '@/common/test-utils';

const SETUP = {
  onboarding_complete: true,
  timezone: 'Asia/Tokyo',
  questions_per_day: 2,
};

describe('library', () => {
  it('reads filters and sort from the URL and writes changes back', async () => {
    const { calls } = fakeApi({
      '/setup': SETUP,
      '/problems': { items: [problemRow()], total: 1, page: 1, page_size: 25 },
      '/topics': topicLevels(),
      '/patterns': [],
      '/lists': [],
    });
    const { router } = routeRender(
      '/library?difficulty=%22Medium%22&sort=%22rating%22&order=%22desc%22&page=2',
    );
    const table = await screen.findByRole('table', { name: 'Problems' });
    expect(
      await within(table).findByRole('link', { name: '1. Two Sum' }),
    ).toBeInTheDocument();

    const first = calls.find((c) => c.path === '/problems');
    expect(Object.fromEntries(first?.query ?? [])).toEqual({
      difficulty: 'Medium',
      sort: 'rating',
      order: 'desc',
      page: '2',
    });

    // A new sort goes back to page 1 and lands in the URL.
    await userEvent.click(
      within(table).getByRole('button', { name: 'Problem' }),
    );
    await waitFor(() =>
      expect(router.state.location.search).toEqual({
        difficulty: 'Medium',
        sort: 'title',
        order: 'asc',
      }),
    );
    expect(
      calls
        .filter((c) => c.path === '/problems')
        .at(-1)
        ?.query.get('sort'),
    ).toBe('title');
  });

  it('is locked during a hidden assessment', async () => {
    fakeApi({
      '/setup': SETUP,
      '/problems': apiErrorResponse(403, 'HIDDEN_ASSESSMENT'),
      '/topics': apiErrorResponse(403, 'HIDDEN_ASSESSMENT'),
      '/patterns': apiErrorResponse(403, 'HIDDEN_ASSESSMENT'),
      '/lists': [],
    });
    routeRender('/library');
    expect(
      await screen.findByText('Locked during your assessment'),
    ).toBeInTheDocument();
  });
});
