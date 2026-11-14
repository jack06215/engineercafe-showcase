import { RouterProvider } from '@tanstack/react-router';

import { AppProviders } from '@/common/providers';
import type { AppRouter } from '@/common/router';

import type { QueryClient } from '@tanstack/react-query';

type Props = {
  router: AppRouter;
  queryClient?: QueryClient;
};

const App = ({ router, queryClient }: Props) => {
  return (
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>
  );
};

export default App;
