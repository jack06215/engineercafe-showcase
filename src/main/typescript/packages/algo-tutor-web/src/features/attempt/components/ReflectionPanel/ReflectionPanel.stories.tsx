import { fn } from 'storybook/test';

import { ReflectionPanel } from './ReflectionPanel';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'attempt/ReflectionPanel',
  component: ReflectionPanel,
  args: { labels: [], takeaway: '', onSave: fn(async () => {}) },
} satisfies Meta<typeof ReflectionPanel>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Empty: Story = {};
export const Filled: Story = {
  args: {
    labels: ['missed_edge_case'],
    takeaway:
      'Check the complement before inserting, or [3,3] pairs with itself.',
  },
};
