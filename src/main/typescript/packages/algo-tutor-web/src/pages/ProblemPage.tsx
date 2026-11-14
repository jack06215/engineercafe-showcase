import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';

import { isApiError } from '@/api/client';
import { patchProblem, patchReview, startAttempt } from '@/api/endpoints';
import { keys, patternsQuery, problemQuery, topicsQuery } from '@/api/queries';
import { QueryView } from '@/components/ui/QueryView';
import { ProblemView } from '@/features/library/components/ProblemView';

type Props = { problemId: string };

export const ProblemPage = ({ problemId }: Props) => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const detail = useQuery(problemQuery(problemId));
  const topics = useQuery(topicsQuery);
  const patterns = useQuery(patternsQuery);
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: keys.problem(problemId) });

  return (
    <QueryView query={detail}>
      {(data) => (
        <ProblemView
          key={data.problem.id}
          detail={data}
          topics={topics.data?.topics ?? []}
          patterns={patterns.data ?? []}
          onPatch={async (patch) => {
            queryClient.setQueryData(
              keys.problem(problemId),
              await patchProblem(problemId, patch),
            );
            void queryClient.invalidateQueries({ queryKey: keys.topics });
          }}
          onReview={async (patch) => {
            try {
              await patchReview(problemId, patch);
            } finally {
              await refresh();
            }
          }}
          onStart={async () => {
            try {
              const started = await startAttempt({ problem_id: problemId });
              await navigate({
                to: '/attempts/$id',
                params: { id: started.id },
              });
            } catch (e) {
              if (isApiError(e, 'ACTIVE_ATTEMPT')) {
                throw new Error(
                  'Another attempt is unfinished. Finish or cancel it first.',
                  { cause: e },
                );
              }
              throw e;
            }
          }}
        />
      )}
    </QueryView>
  );
};
