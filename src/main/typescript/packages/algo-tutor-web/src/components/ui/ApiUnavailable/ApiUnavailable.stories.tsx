import { fn } from 'storybook/test';

import { ApiError } from '@/api/client';

import { ApiUnavailable } from './ApiUnavailable';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'ui/ApiUnavailable',
  component: ApiUnavailable,
  args: {
    error: new ApiError(0, 'UNREACHABLE', 'Failed to fetch'),
    onRetry: fn(),
  },
} satisfies Meta<typeof ApiUnavailable>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Unreachable: Story = {};

export const ServerError: Story = {
  args: { error: new ApiError(404, 'NOT_FOUND', 'Problem not found') },
};
