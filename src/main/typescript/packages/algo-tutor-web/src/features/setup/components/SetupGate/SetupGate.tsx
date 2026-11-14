import Box from '@mui/material/Box';
import LinearProgress from '@mui/material/LinearProgress';
import { useQuery } from '@tanstack/react-query';

import { setupQuery } from '@/api/queries';
import type { SetupState } from '@/api/types';
import { ApiUnavailable } from '@/components/ui/ApiUnavailable';

type Props = {
  children: React.ReactNode;
  // The Setup screen, shown until setup is done.
  setup: (state: SetupState) => React.ReactNode;
};

// SPEC §14: the Setup screen is shown until setup is done, in place of
// every route.
export const SetupGate = ({ children, setup: setupScreen }: Props) => {
  const setup = useQuery(setupQuery);

  if (setup.isPending) {
    return <LinearProgress aria-label="Loading algo_tutor" />;
  }
  if (setup.isError) {
    return (
      <Box sx={{ p: 3 }}>
        <ApiUnavailable
          error={setup.error}
          onRetry={() => void setup.refetch()}
        />
      </Box>
    );
  }
  if (!setup.data.onboarding_complete) {
    return setupScreen(setup.data);
  }
  return children;
};
