import { fn } from 'storybook/test';

import { listDetail, listSummary } from '@/api/fixtures';
import { withRouter } from '@/common/storybook';

import { ListView } from './ListView';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'lists/ListView',
  component: ListView,
  decorators: [withRouter],
  args: {
    detail: listDetail(),
    onPatch: fn(async () => {}),
    onToggleActive: fn(async () => {}),
    onDelete: fn(async () => {}),
  },
} satisfies Meta<typeof ListView>;

export default meta;

type Story = StoryObj<typeof meta>;

export const OwnList: Story = {};
export const Bundled: Story = {
  args: { detail: listDetail({ summary: listSummary() }) },
};
