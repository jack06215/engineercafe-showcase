import { useQuery } from '@tanstack/react-query';

import { patternsQuery } from '@/api/queries';
import { QueryView } from '@/components/ui/QueryView';
import { PatternsView } from '@/features/notebooks/components/PatternsView';

export const PatternsPage = () => {
  const patterns = useQuery(patternsQuery);
  return (
    <QueryView query={patterns}>
      {(data) => <PatternsView patterns={data} />}
    </QueryView>
  );
};
