import { ThemeModeSwitch } from './ThemeModeSwitch';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'layout/ThemeModeSwitch',
  component: ThemeModeSwitch,
} satisfies Meta<typeof ThemeModeSwitch>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
