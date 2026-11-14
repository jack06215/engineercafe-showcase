import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  attempt,
  desk,
  hiddenDesk,
  plan,
  planItem,
  problemBrief,
} from '@/api/fixtures';
import type { Desk } from '@/api/types';
import {
  apiErrorResponse,
  fakeApi,
  type FakeRequest,
  routeRender,
} from '@/common/test-utils';

const SETUP = {
  '/setup': {
    onboarding_complete: true,
    timezone: 'Asia/Tokyo',
    questions_per_day: 2,
  },
};

const TUTOR = {
  enabled: true,
  provider: 'ollama',
  model: 'qwen3.6:35b',
  leaves_machine: false,
  pending_reports: 0,
};

const deskApi = (
  data: Desk,
  routes: Record<string, unknown | ((r: FakeRequest) => unknown)> = {},
) =>
  fakeApi({
    ...SETUP,
    'POST /plans/today/ensure': data.plan,
    'GET /desk': data,
    ...routes,
  });

const row = (title: string) => screen.getByRole('listitem', { name: title });

const openMenu = async (title: string) => {
  await userEvent.click(
    within(row(title)).getByRole('button', {
      name: `More actions for ${title}`,
    }),
  );
};

describe('desk', () => {
  it('ensures today, then shows both lanes with their items', async () => {
    const { calls } = deskApi(desk());
    routeRender('/');

    expect(await screen.findByText(/3 of 3 left today/)).toBeInTheDocument();
    expect(screen.getByText(/1 check due/)).toBeInTheDocument();
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual(
      expect.arrayContaining(['POST /plans/today/ensure', 'GET /desk']),
    );

    const leetcode = screen.getByRole('region', { name: 'LeetCode lane' });
    expect(
      within(leetcode)
        .getAllByRole('listitem')
        .map((li) => li.getAttribute('aria-label')),
    ).toEqual(['Two Sum', 'Longest Consecutive Sequence']);
    expect(within(row('Two Sum')).getByText('Up next')).toBeInTheDocument();
    expect(
      within(row('Longest Consecutive Sequence')).getByText(
        'Transfer check — spot the approach yourself',
      ),
    ).toBeInTheDocument();
    // Plan rows don't link to problem pages: that would show a check's topic.
    expect(within(leetcode).queryByRole('link')).toBeNull();

    const atcoder = screen.getByRole('region', { name: 'AtCoder lane' });
    expect(within(atcoder).getByText('Logs')).toBeInTheDocument();
  });

  it('starts an item and opens its attempt', async () => {
    const { calls } = deskApi(desk(), {
      'POST /attempts': attempt({ id: 'a-new' }),
      'GET /attempts/a-new': attempt({ id: 'a-new' }),
      'POST /attempts/a-new/timer': attempt({ id: 'a-new', version: 2 }),
      'GET /attempts/a-new/hints': { messages: [], strongest_level: null },
      '/tutor/status': TUTOR,
    });
    routeRender('/');

    await screen.findByText(/left today/);
    await userEvent.click(
      within(row('Two Sum')).getByRole('button', { name: 'Start' }),
    );

    expect(
      await screen.findByRole('button', { name: 'Save result' }),
    ).toBeInTheDocument();
    expect(calls.find((c) => c.path === '/attempts')?.body).toEqual({
      problem_id: 'p-two-sum',
      plan_item_id: 'i-1',
      language: 'python',
    });
  });

  it('replaces, skips, postpones and promotes items with the plan version', async () => {
    const { calls } = deskApi(desk(), {
      'POST /plans/plan-1/items/i-2/disposition': (r: FakeRequest) =>
        (r.body as { action: string }).action === 'swap'
          ? apiErrorResponse(409, 'NO_REPLACEMENT')
          : plan([]),
      'POST /plans/plan-1/items/i-2/activate': plan([]),
    });
    routeRender('/');
    await screen.findByText(/left today/);
    const check = 'Longest Consecutive Sequence';

    await openMenu(check);
    await userEvent.click(
      screen.getByRole('menuitem', { name: 'Replace question' }),
    );
    expect(
      await screen.findByText(
        'No other question fits your current training levels.',
      ),
    ).toBeInTheDocument();

    await openMenu(check);
    await userEvent.click(screen.getByRole('menuitem', { name: 'Make next' }));
    await openMenu(check);
    await userEvent.click(screen.getByRole('menuitem', { name: 'Skip today' }));
    await openMenu(check);
    await userEvent.click(screen.getByRole('menuitem', { name: 'Postpone…' }));
    const dialog = await screen.findByRole('dialog');
    const until = within(dialog).getByLabelText('Until');
    await userEvent.clear(until);
    await userEvent.type(until, '2026-11-15');
    await userEvent.click(
      within(dialog).getByRole('button', { name: 'Postpone' }),
    );

    await waitFor(() =>
      expect(
        calls
          .filter(
            (c) =>
              c.method === 'POST' && c.path.startsWith('/plans/plan-1/items'),
          )
          .map((c) => [c.path.split('/').at(-1), c.body]),
      ).toEqual([
        ['disposition', { version: 3, action: 'swap' }],
        ['activate', { version: 3 }],
        ['disposition', { version: 3, action: 'skip' }],
        [
          'disposition',
          { version: 3, action: 'snooze', snooze_until: '2026-11-15' },
        ],
      ]),
    );
  });

  it('moves an item within its lane', async () => {
    const { calls } = deskApi(desk(), {
      'POST /plans/plan-1/reorder': plan([]),
    });
    routeRender('/');
    await screen.findByText(/left today/);

    await openMenu('Longest Consecutive Sequence');
    await userEvent.click(screen.getByRole('menuitem', { name: 'Move up' }));
    await waitFor(() =>
      expect(
        calls.find((c) => c.path === '/plans/plan-1/reorder')?.body,
      ).toEqual({
        version: 3,
        lane: 'leetcode',
        item_ids: ['i-2', 'i-1'],
      }),
    );
  });

  it('records Too easy on a finished item, and lists plan changes', async () => {
    const data = desk({
      plan: plan([
        planItem({
          status: 'completed',
          attempt_id: 'a-done',
          signals: { accepted_first_try: null, difficulty: null },
        }),
        planItem({
          id: 'i-skipped',
          position: 1,
          status: 'skipped',
          disposition: 'snooze',
          problem: problemBrief({ id: 'p-x', title: 'Group Anagrams' }),
        }),
      ]),
    });
    const { calls } = deskApi(data, {
      'PATCH /attempts/a-done/signals': attempt({ id: 'a-done' }),
    });
    routeRender('/');
    await screen.findByText(/left today/);

    expect(within(row('Two Sum')).getByText('Done')).toBeInTheDocument();
    await userEvent.click(
      within(row('Two Sum')).getByRole('button', { name: 'Too easy' }),
    );
    await waitFor(() =>
      expect(
        calls.find((c) => c.path === '/attempts/a-done/signals')?.body,
      ).toEqual({
        difficulty: 'too_easy',
      }),
    );
    expect(screen.getByText('Plan changes (1)')).toBeInTheDocument();
  });

  it('shows only "Assessment in progress" during a hidden assessment', async () => {
    fakeApi({
      ...SETUP,
      'POST /plans/today/ensure': apiErrorResponse(403, 'HIDDEN_ASSESSMENT'),
      'GET /desk': hiddenDesk(),
      'GET /attempts/a-check': attempt({ id: 'a-check', context: 'mixed' }),
      'POST /attempts/a-check/timer': attempt({ id: 'a-check', version: 2 }),
      'GET /attempts/a-check/hints': { messages: [], strongest_level: null },
      '/tutor/status': TUTOR,
    });
    routeRender('/');

    expect(
      await screen.findByRole('heading', { name: 'Assessment in progress' }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'LeetCode lane' })).toBeNull();
    expect(screen.queryByText(/left today/)).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: 'Resume' }));
    expect(
      await screen.findByRole('button', { name: 'Save result' }),
    ).toBeInTheDocument();
  });

  it('offers the bank and the library when nothing is planned', async () => {
    deskApi(
      desk({ plan: plan([]), bank_empty: true, left_today: 0, total_today: 0 }),
    );
    routeRender('/');
    expect(
      await screen.findByText('No questions at your level yet'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Get the problem bank' }),
    ).toHaveAttribute('href', '/settings');
    vi.unstubAllGlobals();
  });
});
