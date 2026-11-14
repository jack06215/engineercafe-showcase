import { fn } from 'storybook/test';

import { NOW } from '@/api/fixtures';

import { HintPanel } from './HintPanel';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'attempt/HintPanel',
  component: HintPanel,
  args: {
    messages: [],
    onSend: fn(async () => {}),
  },
} satisfies Meta<typeof HintPanel>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Empty: Story = {};

export const Conversation: Story = {
  args: {
    messages: [
      {
        id: 'm1',
        position: 0,
        role: 'learner',
        text: "My nested loop times out and I don't see how to avoid it.",
        stuck_at_seconds: 512,
        level: null,
        hint: null,
        analysis: null,
        created_at: NOW,
      },
      {
        id: 'm2',
        position: 1,
        role: 'tutor',
        text: 'For each number, what **other** value would complete the pair? Could you look that up faster than scanning?',
        stuck_at_seconds: null,
        level: 'small',
        hint: 'Think about what complements each number.',
        analysis: 'A correct O(n²) scan; the inner loop is the bottleneck.',
        created_at: NOW,
      },
    ],
  },
};

export const TutorOff: Story = {
  args: {
    unavailable: 'Algo-chan is off: tutor.enabled is false in config.yaml.',
  },
};
