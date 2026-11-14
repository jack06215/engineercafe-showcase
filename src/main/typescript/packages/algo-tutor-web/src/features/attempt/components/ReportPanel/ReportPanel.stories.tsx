import { fn } from 'storybook/test';

import { report } from '@/api/fixtures';

import { ReportPanel } from './ReportPanel';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'attempt/ReportPanel',
  component: ReportPanel,
  args: { report: report(), onRequest: fn() },
} satisfies Meta<typeof ReportPanel>;

export default meta;

type Story = StoryObj<typeof meta>;

export const NoReport: Story = {};
export const Generating: Story = {
  args: { report: report({ status: 'generating' }) },
};
export const Done: Story = {
  args: {
    report: report({
      status: 'done',
      summary: 'A clean one-pass hash map solution.',
      strengths:
        'You checked the complement **before** inserting, so `[3, 3]` works.',
      improvements: 'Name `d` something that says what it maps.',
      complexity: 'O(n) time, O(n) space.',
      practice: 'Try 3Sum next: the same idea, one level up.',
      model: 'qwen3.6:35b',
    }),
  },
};
export const Failed: Story = {
  args: { report: report({ status: 'failed', error_kind: 'unavailable' }) },
};
