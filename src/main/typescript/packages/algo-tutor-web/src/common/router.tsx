import LinearProgress from '@mui/material/LinearProgress';
import { createRouter, type RouterHistory } from '@tanstack/react-router';

import { routeTree } from '@/routeTree.gen';

type Options = {
  // Browser history by default; tests pass a memory history.
  history?: RouterHistory;
};

// The router over the generated route tree (src/routes/ → routeTree.gen.ts).
export const createAppRouter = (options: Options = {}) => {
  return createRouter({
    routeTree,
    ...options,
    // Shown while a route's code-split chunk loads, if that takes a while.
    defaultPendingComponent: () => (
      <LinearProgress aria-label="Loading the page" />
    ),
  });
};

export type AppRouter = ReturnType<typeof createAppRouter>;

// Types Link, useNavigate, useSearch, … against this app's routes.
declare module '@tanstack/react-router' {
  interface Register {
    router: AppRouter;
  }
}
