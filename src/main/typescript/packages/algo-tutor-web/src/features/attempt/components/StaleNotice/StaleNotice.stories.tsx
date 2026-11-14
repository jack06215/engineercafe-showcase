import { fn } from 'storybook/test';

import { StaleNotice } from './StaleNotice';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'attempt/StaleNotice',
  component: StaleNotice,
  args: {
    unsavedText: 'def two_sum(nums, target):\n    ...',
    onReload: fn(),
  },
} satisfies Meta<typeof StaleNotice>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
