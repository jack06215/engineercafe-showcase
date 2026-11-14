import { useQuery } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';

import { topicsQuery } from '@/api/queries';
import { QueryView } from '@/components/ui/QueryView';
import { TopicsView } from '@/features/notebooks/components/TopicsView';

export const TopicsPage = () => {
  const navigate = useNavigate();
  const topics = useQuery(topicsQuery);
  return (
    <QueryView query={topics}>
      {(levels) => (
        <TopicsView
          levels={levels}
          onTopic={(id) => void navigate({ to: '/topics/$id', params: { id } })}
        />
      )}
    </QueryView>
  );
};
