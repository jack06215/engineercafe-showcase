import { fn } from 'storybook/test';

import { FinishForm } from './FinishForm';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'attempt/FinishForm',
  component: FinishForm,
  args: {
    stopwatchSeconds: 754,
    strongestHint: null,
    hasCode: true,
    onSubmit: fn(async () => {}),
  },
} satisfies Meta<typeof FinishForm>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};

// Help follows the strongest hint Algo-chan gave.
export const AfterAMajorHint: Story = { args: { strongestHint: 'major' } };

export const NoCodeYet: Story = { args: { hasCode: false } };
