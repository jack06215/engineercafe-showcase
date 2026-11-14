import { useQuery } from '@tanstack/react-query';

import { mistakesQuery } from '@/api/queries';
import { QueryView } from '@/components/ui/QueryView';
import { MistakesView } from '@/features/notebooks/components/MistakesView';

export const MistakesPage = () => {
  const mistakes = useQuery(mistakesQuery);
  return (
    <QueryView query={mistakes}>
      {(data) => <MistakesView items={data.items} />}
    </QueryView>
  );
};
