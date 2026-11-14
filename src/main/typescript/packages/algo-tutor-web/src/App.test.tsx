import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  attempt,
  listSummary,
  problemDetail,
  problemRow,
  topicLevels,
} from '@/api/fixtures';
import { routeRender, stubApi } from '@/common/test-utils';

const SETUP_DONE = {
  onboarding_complete: true,
  timezone: 'Asia/Tokyo',
  questions_per_day: 2,
};

const API = {
  '/setup': SETUP_DONE,
  '/problems': { items: [problemRow()], total: 1, page: 1, page_size: 25 },
  '/problems/p-123': problemDetail(),
  '/topics': topicLevels(),
  '/patterns': [],
  '/lists': [listSummary()],
  '/tutor/status': {
    enabled: true,
    provider: 'ollama',
    model: 'qwen3.6:35b',
    leaves_machine: false,
    pending_reports: 0,
  },
  '/attempts/a-42': attempt({ id: 'a-42' }),
  '/attempts/a-42/timer': attempt({ id: 'a-42', version: 2 }),
  '/attempts/a-42/hints': { messages: [], strongest_level: null },
};

describe('app shell', () => {
  it('shows the sidebar with the current page selected, and navigates', async () => {
    stubApi(API);
    routeRender('/library');

    expect(
      await screen.findByRole('heading', { name: 'Library' }),
    ).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(
      within(nav)
        .getAllByRole('link')
        .map((link) => link.textContent),
    ).toEqual([
      'Desk',
      'Library',
      'Lists',
      'Topics',
      'Patterns',
      'Mistakes',
      'Settings',
    ]);
    expect(within(nav).getByRole('link', { name: 'Library' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(nav).getByRole('link', { name: 'Desk' })).not.toHaveAttribute(
      'aria-current',
    );

    await userEvent.click(within(nav).getByRole('link', { name: 'Topics' }));
    expect(
      await screen.findByRole('heading', { name: 'Topics' }),
    ).toBeInTheDocument();
  });

  it('passes route params to detail pages', async () => {
    const fetchMock = stubApi(API);
    routeRender('/library/p-123');
    expect(
      await screen.findByRole('heading', { name: '1. Two Sum' }),
    ).toBeInTheDocument();
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toContain(
      '/api/problems/p-123',
    );
  });

  it('shows the attempt page full-window, without the sidebar', async () => {
    stubApi(API);
    routeRender('/attempts/a-42');
    expect(
      await screen.findByRole('heading', { name: 'Two Sum' }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Main' })).toBeNull();
    expect(
      screen.getByRole('link', { name: 'Back to the desk' }),
    ).toHaveAttribute('href', '/');
  });

  it('shows Setup in place of every page until setup is done', async () => {
    stubApi({ '/setup': { ...SETUP_DONE, onboarding_complete: false } });
    routeRender('/topics');
    expect(
      await screen.findByRole('heading', { name: 'Set up algo_tutor' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Asia\/Tokyo/)).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Main' })).toBeNull();
  });

  it('says how to start the API when it is down', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    );
    routeRender('/');
    expect(
      await screen.findByText("Can't reach the algo_tutor API"),
    ).toBeInTheDocument();
    expect(
      screen.getByText('bazel run //packages/algo_tutor:serve'),
    ).toBeInTheDocument();
  });

  it('shows a locked notice, not an error, during a hidden assessment', async () => {
    const { apiErrorResponse } = await import('@/common/test-utils');
    stubApi({
      '/setup': SETUP_DONE,
      '/topics': apiErrorResponse(403, 'HIDDEN_ASSESSMENT'),
    });
    routeRender('/topics');
    expect(
      await screen.findByText('Locked during your assessment'),
    ).toBeInTheDocument();
  });

  it('has a not-found page', async () => {
    stubApi(API);
    routeRender('/nowhere');
    expect(
      await screen.findByRole('heading', { name: 'Page not found' }),
    ).toBeInTheDocument();
  });
});
