import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { attempt, NOW, report } from '@/api/fixtures';
import type { AttemptOut } from '@/api/types';
import {
  apiErrorResponse,
  fakeApi,
  type FakeRequest,
  routeRender,
} from '@/common/test-utils';

const SETUP = {
  onboarding_complete: true,
  timezone: 'Asia/Tokyo',
  questions_per_day: 2,
};

type Body = Record<string, unknown>;

// A fake of the attempt routes over one record: every write checks the
// version and bumps it, as the API does.
const attemptServer = (initial: AttemptOut) => {
  let current = initial;
  const bump = (patch: Partial<AttemptOut> = {}) => {
    current = { ...current, ...patch, version: current.version + 1 };
    return current;
  };
  const versioned =
    (write: (body: Body) => unknown) =>
    ({ body }: FakeRequest) =>
      (body as Body).version === current.version
        ? write(body as Body)
        : apiErrorResponse(
            409,
            'STALE',
            'Attempt changed elsewhere; reload it',
          );
  const api = fakeApi({
    '/setup': SETUP,
    '/tutor/status': {
      enabled: true,
      provider: 'ollama',
      model: 'qwen3.6:35b',
      leaves_machine: false,
      pending_reports: 0,
    },
    '/patterns': [],
    'GET /attempts/a-1': () => current,
    'GET /attempts/a-1/hints': { messages: [], strongest_level: null },
    'POST /attempts/a-1/timer': versioned(() => bump()),
    'PATCH /attempts/a-1/draft': versioned((body) => {
      const { version: _v, ...fields } = body;
      return bump(fields as Partial<AttemptOut>);
    }),
    'POST /attempts/a-1/finish': versioned((body) => ({
      attempt: bump({
        status: 'completed',
        outcome: body.outcome as AttemptOut['outcome'],
        help: body.help as AttemptOut['help'],
        active_seconds: 105,
        finished_at: NOW,
        next_review_date: '2026-11-22',
        takeaway: '',
        mistake_labels: [],
        signals: { accepted_first_try: null, difficulty: null },
        patterns: [],
        report: report({ status: 'pending' }),
      }),
      next_review_date: '2026-11-22',
      review_stage: 'mixed',
    })),
  });
  return {
    ...api,
    get current() {
      return current;
    },
    // Someone else wrote meanwhile.
    changeElsewhere(patch: Partial<AttemptOut>) {
      bump(patch);
    },
  };
};

const open = async () => {
  routeRender('/attempts/a-1');
  return screen.findByRole('button', { name: 'Save result' });
};

describe('attempt page', () => {
  it('shows the server-kept time and sends a heartbeat on open', async () => {
    const server = attemptServer(
      attempt({ active_seconds: 105, code: 'x', notes: '' }),
    );
    await open();
    expect(screen.getByLabelText('Active time')).toHaveTextContent('01:45');
    await waitFor(() =>
      expect(server.calls.some((c) => c.path === '/attempts/a-1/timer')).toBe(
        true,
      ),
    );
    expect(screen.getByRole('button', { name: 'Pause' })).toBeInTheDocument();
  });

  it('asks whether to count a gap, and resumes with the answer', async () => {
    const server = attemptServer(
      attempt({
        status: 'paused',
        needs_gap_decision: true,
        gap_seconds: 600,
        running_since: null,
      }),
    );
    await open();
    expect(screen.getByText(/went quiet for 10:00/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Count it' }));
    await waitFor(() =>
      expect(
        server.calls.find((c) => c.path === '/attempts/a-1/timer')?.body,
      ).toMatchObject({ action: 'resume', include_gap: true }),
    );
  });

  it('autosaves notes after a pause in typing, with the latest version', async () => {
    const server = attemptServer(attempt({ code: 'x' }));
    await open();
    // The heartbeat on open has bumped the version first.
    await waitFor(() => expect(server.current.version).toBe(2));

    await userEvent.type(screen.getByLabelText('Notes'), 'two pass');
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText('Saved')).toBeInTheDocument(), {
      timeout: 3000,
    });
    const drafts = server.calls.filter((c) => c.path === '/attempts/a-1/draft');
    expect(drafts).toHaveLength(1);
    expect(drafts[0].body).toEqual({ version: 2, notes: 'two pass' });
    expect(server.current.notes).toBe('two pass');
  });

  it('freezes on 409 and offers to reload the saved version', async () => {
    const server = attemptServer(attempt({ code: 'x', notes: 'mine' }));
    await open();
    await waitFor(() => expect(server.current.version).toBe(2));
    server.changeElsewhere({ notes: 'from the other tab' });

    await userEvent.type(screen.getByLabelText('Notes'), '!');
    expect(
      await screen.findByText('Not saved', {}, { timeout: 3000 }),
    ).toBeInTheDocument();
    const notice = screen.getByRole('alert');
    expect(
      within(notice).getByRole('button', { name: 'Copy unsaved text' }),
    ).toBeInTheDocument();

    await userEvent.click(
      within(notice).getByRole('button', { name: 'Reload saved version' }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText('Notes')).toHaveValue('from the other tab'),
    );
    expect(screen.getByText('Saved')).toBeInTheDocument();
  });

  it('prefills Help from the strongest hint and finishes with an idempotency key', async () => {
    const server = attemptServer(
      attempt({
        code: 'def f(): pass',
        strongest_hint: 'small',
        active_seconds: 105,
      }),
    );
    await open();
    const form = screen.getByRole('form', { name: 'Finish the attempt' });
    expect(within(form).getByLabelText('Help used')).toHaveTextContent(
      'Small hint',
    );
    expect(
      within(form).getByText(
        'Leaving Help as Unknown schedules a repair tomorrow',
      ),
    ).toBeInTheDocument();

    await userEvent.click(within(form).getByLabelText('Stopped'));
    const time = within(form).getByLabelText(/Time/);
    await userEvent.clear(time);
    await userEvent.type(time, '12:34');
    await userEvent.click(
      within(form).getByRole('button', { name: 'Save result' }),
    );

    expect(
      await screen.findByRole('heading', { name: 'Attempt saved' }),
    ).toBeInTheDocument();
    const finish = server.calls.find((c) => c.path === '/attempts/a-1/finish');
    expect(finish?.headers['Idempotency-Key']).toMatch(/^[A-Za-z0-9_.:-]+$/);
    expect(finish?.body).toMatchObject({
      outcome: 'stopped',
      help: 'small',
      time: '12:34',
      confidence: null,
      review_choice: 'recommended',
      review_date: null,
      language: 'python',
      code: 'def f(): pass',
    });
    expect(screen.getByText('Waiting for Algo-chan…')).toBeInTheDocument();
  });

  it('refuses to finish without code, and refuses a bad time', async () => {
    const server = attemptServer(attempt({ code: '' }));
    await open();
    const form = screen.getByRole('form', { name: 'Finish the attempt' });
    const time = within(form).getByLabelText(/Time/);
    await userEvent.clear(time);
    await userEvent.type(time, '7:5');
    await userEvent.click(
      within(form).getByRole('button', { name: 'Save result' }),
    );

    expect(
      within(form).getByText(/Paste or write your solution code first/),
    ).toBeInTheDocument();
    expect(within(form).getByText(/two-digit seconds/)).toBeInTheDocument();
    expect(server.calls.some((c) => c.path === '/attempts/a-1/finish')).toBe(
      false,
    );
  });

  it('explains a vanished linked file at finish, without freezing the page', async () => {
    const linked = attempt({
      code: 'x',
      solution_path: 'leetcode/src/0001_two_sum_easy.py',
    });
    const { calls } = fakeApi({
      '/setup': SETUP,
      '/tutor/status': {
        enabled: false,
        provider: 'ollama',
        model: 'qwen3.6:35b',
        leaves_machine: false,
        pending_reports: 0,
      },
      'GET /attempts/a-1': linked,
      'GET /attempts/a-1/hints': { messages: [], strongest_level: null },
      'POST /attempts/a-1/timer': { ...linked, version: 2 },
      'POST /attempts/a-1/finish': apiErrorResponse(
        400,
        'SOLUTION_FILE_MISSING',
        'gone',
      ),
    });
    await open();
    expect(
      screen.getByText(/leetcode\/src\/0001_two_sum_easy.py/),
    ).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Save result' }));
    expect(
      await screen.findByText(
        /0001_two_sum_easy.py is missing. Fix the path or switch to the editor/,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText('Not saved')).toBeNull();
    expect(calls.some((c) => c.path === '/attempts/a-1/finish')).toBe(true);
    // With the tutor off, the hint panel says so instead of a form.
    expect(screen.getByText(/Algo-chan is off/)).toBeInTheDocument();
  });
});
