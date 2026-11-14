import { SaveStatus } from './SaveStatus';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'attempt/SaveStatus',
  component: SaveStatus,
  args: { status: 'saved' },
} satisfies Meta<typeof SaveStatus>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Saved: Story = {};
export const Dirty: Story = { args: { status: 'dirty' } };
export const Saving: Story = { args: { status: 'saving' } };
export const NotSaved: Story = { args: { status: 'error' } };
