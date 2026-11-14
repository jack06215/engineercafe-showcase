import Typography from '@mui/material/Typography';
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { useState } from 'react';

import { AppShell } from './AppShell';

import type { Meta, StoryObj } from '@storybook/react-vite';

// The shell's links need a router. This one has a single catch-all page, on
// a memory history, so clicking around stays inside the story.
const ShellAt = ({ path }: { path: string }) => {
  const [router] = useState(() =>
    createRouter({
      routeTree: createRootRoute({
        component: () => (
          <AppShell>
            <Typography variant="h4" component="h1">
              Page content
            </Typography>
          </AppShell>
        ),
      }),
      history: createMemoryHistory({ initialEntries: [path] }),
    }),
  );
  return <RouterProvider router={router} />;
};

const meta = {
  title: 'layout/AppShell',
  component: ShellAt,
  args: { path: '/' },
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof ShellAt>;

export default meta;

type Story = StoryObj<typeof meta>;

export const OnTheDesk: Story = {};

export const OnTheLibrary: Story = { args: { path: '/library' } };
