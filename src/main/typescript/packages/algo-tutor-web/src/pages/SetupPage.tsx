import Box from '@mui/material/Box';
import { useQueryClient } from '@tanstack/react-query';

import { postSetup } from '@/api/endpoints';
import type { SetupState } from '@/api/types';
import { SetupForm } from '@/features/settings/components/SetupForm';

type Props = {
  state: SetupState;
};

export const SetupPage = ({ state }: Props) => {
  const queryClient = useQueryClient();
  return (
    <Box sx={{ p: 2 }}>
      <SetupForm
        state={state}
        onSubmit={async (body) => {
          await postSetup(body);
          await queryClient.invalidateQueries();
        }}
      />
    </Box>
  );
};
