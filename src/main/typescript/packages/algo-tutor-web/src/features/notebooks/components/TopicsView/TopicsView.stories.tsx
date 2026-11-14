import { fn } from 'storybook/test';

import { topicLevels } from '@/api/fixtures';
import { withRouter } from '@/common/storybook';

import { TopicsView } from './TopicsView';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'notebooks/TopicsView',
  component: TopicsView,
  decorators: [withRouter],
  args: { levels: topicLevels(), onTopic: fn() },
} satisfies Meta<typeof TopicsView>;

export default meta;

type Story = StoryObj<typeof meta>;

export const FreshStart: Story = {};
