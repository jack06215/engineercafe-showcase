import { fn } from 'storybook/test';

import { Stopwatch } from './Stopwatch';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'attempt/Stopwatch',
  component: Stopwatch,
  args: {
    seconds: 754,
    running: true,
    paused: false,
    gapPending: false,
    gapSeconds: 0,
    onPause: fn(),
    onResume: fn(),
  },
} satisfies Meta<typeof Stopwatch>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Running: Story = {};

export const Paused: Story = {
  args: { running: false, paused: true },
};

export const GapQuestion: Story = {
  args: { running: false, paused: true, gapPending: true, gapSeconds: 1325 },
};
