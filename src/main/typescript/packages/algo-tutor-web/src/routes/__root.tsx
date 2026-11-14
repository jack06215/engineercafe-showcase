import { createRootRoute, Outlet } from '@tanstack/react-router';

import { DevelopmentTools } from '@/components/utils/development-tools';
import { SetupGate } from '@/features/setup/components/SetupGate';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { SetupPage } from '@/pages/SetupPage';

export const Route = createRootRoute({
  component: RootLayout,
  notFoundComponent: NotFoundPage,
});

// Every route waits for setup to be done (SPEC §14). The sidebar comes from
// the `_shell` layout; the attempt page sits outside it, full-window.
function RootLayout() {
  return (
    <>
      <SetupGate setup={(state) => <SetupPage state={state} />}>
        <Outlet />
      </SetupGate>
      <DevelopmentTools />
    </>
  );
}
