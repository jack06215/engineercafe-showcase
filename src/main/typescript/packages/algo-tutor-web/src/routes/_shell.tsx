import { createFileRoute, Outlet } from '@tanstack/react-router';

import { AppShell } from '@/components/layout/AppShell';

// The sidebar around every page but the attempt page. Pathless: it adds
// nothing to the URL.
export const Route = createFileRoute('/_shell')({
  component: () => (
    <AppShell>
      <Outlet />
    </AppShell>
  ),
});
