import { fn } from 'storybook/test';

import { problemDetail } from '@/api/fixtures';
import { withRouter } from '@/common/storybook';

import { ProblemView } from './ProblemView';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'library/ProblemView',
  component: ProblemView,
  decorators: [withRouter],
  args: {
    detail: problemDetail(),
    topics: [
      { id: 'array', name: 'Array' },
      { id: 'hash-table', name: 'Hash Table' },
    ],
    patterns: [
      {
        id: '02_two_pointers',
        name: 'Two Pointers',
        position: 2,
        missing: false,
        problems: 4,
      },
    ],
    onPatch: fn(async () => {}),
    onReview: fn(async () => {}),
    onStart: fn(async () => {}),
  },
} satisfies Meta<typeof ProblemView>;

export default meta;

type Story = StoryObj<typeof meta>;

export const TwoSum: Story = {};

export const NeverAttempted: Story = {
  args: {
    detail: problemDetail({
      attempts: [],
      review: null,
      topic_overridden: true,
    }),
  },
};
