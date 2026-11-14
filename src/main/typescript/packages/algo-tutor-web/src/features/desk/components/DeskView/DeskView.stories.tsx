import { fn } from 'storybook/test';

import { desk, hiddenDesk, plan, planItem } from '@/api/fixtures';
import { withRouter } from '@/common/storybook';

import { DeskView } from './DeskView';

import type { Meta, StoryObj } from '@storybook/react-vite';

const actions = {
  start: fn(),
  resume: fn(),
  makeNext: fn(),
  replace: fn(),
  postpone: fn(),
  skip: fn(),
  move: fn(),
  cancel: fn(),
  signal: fn(),
  resumeAttempt: fn(),
  replan: fn(),
};

const meta = {
  title: 'desk/DeskView',
  component: DeskView,
  decorators: [withRouter],
  args: {
    desk: desk(),
    actions,
    now: new Date('2026-11-08T09:00:00'),
  },
} satisfies Meta<typeof DeskView>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Today: Story = {};

export const InProgressAndDone: Story = {
  args: {
    desk: desk({
      active_attempt: {
        id: 'a-1',
        problem_title: 'Valid Anagram',
        context: 'targeted',
        status: 'active',
      },
      plan: plan([
        planItem({
          status: 'completed',
          attempt_id: 'a-0',
          signals: { accepted_first_try: true, difficulty: 'too_easy' },
        }),
        planItem({
          id: 'i-2',
          position: 1,
          attempt_id: 'a-1',
          problem: {
            ...planItem().problem,
            id: 'p-va',
            title: 'Valid Anagram',
          },
        }),
        planItem({
          id: 'i-3',
          position: 2,
          status: 'skipped',
          disposition: 'swap',
        }),
      ]),
      left_today: 1,
      total_today: 2,
    }),
  },
};

export const HiddenAssessment: Story = { args: { desk: hiddenDesk() } };

export const NothingPlanned: Story = {
  args: { desk: desk({ plan: plan([]), bank_empty: true }) },
};
