import Box from '@mui/material/Box';
import { useQuery } from '@tanstack/react-query';

import { attemptQuery } from '@/api/queries';
import { QueryView } from '@/components/ui/QueryView';
import { AttemptScreen } from '@/features/attempt/components/AttemptScreen';

type Props = { attemptId: string };

// Full-window, without the sidebar (SPEC §14).
export const AttemptPage = ({ attemptId }: Props) => {
  // Loaded fresh on every visit, then never refetched: from then on the
  // attempt's write lane holds the record.
  const attempt = useQuery({
    ...attemptQuery(attemptId),
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
  });
  return (
    <Box sx={{ p: { xs: 2, md: 3 } }}>
      <QueryView query={attempt}>
        {(data) => <AttemptScreen key={data.id} initial={data} />}
      </QueryView>
    </Box>
  );
};
