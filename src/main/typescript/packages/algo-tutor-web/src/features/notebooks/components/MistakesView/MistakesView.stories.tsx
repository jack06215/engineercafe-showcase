import { NOW, problemBrief } from '@/api/fixtures';
import { withRouter } from '@/common/storybook';

import { MistakesView } from './MistakesView';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'notebooks/MistakesView',
  component: MistakesView,
  decorators: [withRouter],
  args: {
    items: [
      {
        attempt_id: 'a-1',
        problem: problemBrief(),
        finished_at: NOW,
        mistake_labels: ['missed_edge_case'],
        takeaway: 'Check the complement before inserting the number itself.',
      },
      {
        attempt_id: 'a-2',
        problem: problemBrief({ id: 'p-2', title: 'Trapping Rain Water' }),
        finished_at: NOW,
        mistake_labels: ['wrong_approach', 'implementation_bug'],
        takeaway: '',
      },
    ],
  },
} satisfies Meta<typeof MistakesView>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Lessons: Story = {};
export const Empty: Story = { args: { items: [] } };
