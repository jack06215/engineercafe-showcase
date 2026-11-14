import { fn } from 'storybook/test';

import { notebook, topicDetail } from '@/api/fixtures';
import { withRouter } from '@/common/storybook';

import { TopicView } from './TopicView';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'notebooks/TopicView',
  component: TopicView,
  decorators: [withRouter],
  args: {
    detail: topicDetail(),
    onSave: fn(async () => notebook({ version: 2 })),
    loadSaved: fn(async () => notebook()),
  },
} satisfies Meta<typeof TopicView>;

export default meta;

type Story = StoryObj<typeof meta>;

export const HashTable: Story = {};
