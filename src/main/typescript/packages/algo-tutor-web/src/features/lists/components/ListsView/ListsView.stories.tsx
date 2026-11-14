import { fn } from 'storybook/test';

import { listSummary } from '@/api/fixtures';
import { withRouter } from '@/common/storybook';

import { ListsView } from './ListsView';

import type { Meta, StoryObj } from '@storybook/react-vite';

const meta = {
  title: 'lists/ListsView',
  component: ListsView,
  decorators: [withRouter],
  args: {
    lists: [
      listSummary(),
      listSummary({
        id: 'l-tessoku',
        name: 'Tessoku book, chapter 1',
        source: 'atcoder',
        kind: 'pack',
        origin: null,
        active: false,
        done: 3,
        total: 20,
      }),
    ],
    onFollow: fn(),
    onToggleActive: fn(),
    onPreview: fn(async () => ({
      groups: [],
      unresolved: [],
      unresolved_reasons: [],
    })),
    onCreate: fn(async () => ({
      lists: [],
      unresolved: [],
      unresolved_reasons: [],
    })),
    onImport: fn(),
  },
} satisfies Meta<typeof ListsView>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const NoListsYet: Story = { args: { lists: [] } };
