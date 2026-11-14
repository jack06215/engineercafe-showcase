import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { useState } from 'react';
import { fn } from 'storybook/test';

import { listSummary, problemBrief, problemRow } from '@/api/fixtures';

import { LibraryView } from './LibraryView';

import type { Meta, StoryObj } from '@storybook/react-vite';

type Props = React.ComponentProps<typeof LibraryView>;

// Rows link to problem pages, so the view needs a router.
const WithRouter = (props: Props) => {
  const [router] = useState(() =>
    createRouter({
      routeTree: createRootRoute({
        component: () => <LibraryView {...props} />,
      }),
      history: createMemoryHistory({ initialEntries: ['/library'] }),
    }),
  );
  return <RouterProvider router={router} />;
};

const meta = {
  title: 'library/LibraryView',
  component: WithRouter,
  args: {
    search: {},
    onSearch: fn(),
    topics: [{ id: 'hash-table', name: 'Hash Table' }],
    patterns: [],
    lists: [listSummary()],
    page: {
      items: [
        problemRow(),
        problemRow({
          problem: problemBrief({
            id: 'p-2',
            title: 'Longest Consecutive Sequence',
            number: 128,
            difficulty: 'Medium',
            rating: { value: 1610, estimated: false },
          }),
          latest_outcome: null,
          latest_active_seconds: null,
          latest_confidence: null,
          next_review_date: null,
        }),
      ],
      total: 2,
      page: 1,
      page_size: 25,
    },
  },
} satisfies Meta<typeof WithRouter>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Empty: Story = {
  args: { page: { items: [], total: 0, page: 1, page_size: 25 } },
};
