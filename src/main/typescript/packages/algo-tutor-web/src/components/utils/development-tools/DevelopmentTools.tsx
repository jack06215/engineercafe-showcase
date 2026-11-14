import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { TanStackRouterDevtools } from '@tanstack/react-router-devtools';

// The TanStack Router and Query devtools, as toggle buttons in the corners.
// Both packages render nothing unless NODE_ENV is "development", so they're
// absent from tests and production builds. Rendered by the root route, inside
// both the router and the query client.
export const DevelopmentTools = () => {
  return (
    <>
      <TanStackRouterDevtools position="bottom-left" />
      <ReactQueryDevtools buttonPosition="bottom-right" />
    </>
  );
};
