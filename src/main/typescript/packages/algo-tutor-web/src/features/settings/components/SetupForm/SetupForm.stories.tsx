import { fn } from 'storybook/test';

import { SetupForm } from './SetupForm';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'settings/SetupForm',
  component: SetupForm,
  args: {
    state: {
      onboarding_complete: false,
      timezone: 'Asia/Tokyo',
      questions_per_day: 2,
    },
    onSubmit: fn(async () => {}),
  },
} satisfies Meta<typeof SetupForm>;

export default meta;

type Story = StoryObj<typeof meta>;

export const FirstRun: Story = {};
