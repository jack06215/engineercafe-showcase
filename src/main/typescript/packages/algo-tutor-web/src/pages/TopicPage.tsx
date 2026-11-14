import { useQuery, useQueryClient } from '@tanstack/react-query';

import { getTopic, patchTopicNotebook } from '@/api/endpoints';
import { keys, topicQuery } from '@/api/queries';
import { QueryView } from '@/components/ui/QueryView';
import { TopicView } from '@/features/notebooks/components/TopicView';

type Props = { topicId: string };

export const TopicPage = ({ topicId }: Props) => {
  const queryClient = useQueryClient();
  // The notebook editor owns the text once loaded; don't refetch under it.
  const topic = useQuery({
    ...topicQuery(topicId),
    refetchOnWindowFocus: false,
  });
  return (
    <QueryView query={topic}>
      {(detail) => (
        <TopicView
          key={detail.level.id}
          detail={detail}
          onSave={async (patch) => {
            const saved = await patchTopicNotebook(topicId, patch);
            queryClient.setQueryData(keys.topic(topicId), {
              ...detail,
              notebook: saved,
            });
            return saved;
          }}
          loadSaved={async () => (await getTopic(topicId)).notebook}
        />
      )}
    </QueryView>
  );
};
