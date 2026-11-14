import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import { useState } from 'react';

import type { Decorator } from '@storybook/react-vite';

const StoryRouter = ({ story }: { story: () => React.ReactNode }) => {
  const [router] = useState(() =>
    createRouter({
      routeTree: createRootRoute({ component: () => story() }),
      history: createMemoryHistory({ initialEntries: ['/'] }),
    }),
  );
  return <RouterProvider router={router} />;
};

// For stories of components with router links or blockers: one catch-all
// route on a memory history, so clicking a link stays inside the story.
export const withRouter: Decorator = (Story) => (
  <StoryRouter story={() => <Story />} />
);
