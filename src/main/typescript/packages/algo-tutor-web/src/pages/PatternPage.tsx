import { useQuery, useQueryClient } from '@tanstack/react-query';

import { getPattern, patchPatternNotebook } from '@/api/endpoints';
import { keys, patternQuery } from '@/api/queries';
import { QueryView } from '@/components/ui/QueryView';
import { PatternView } from '@/features/notebooks/components/PatternView';

type Props = { patternId: string };

export const PatternPage = ({ patternId }: Props) => {
  const queryClient = useQueryClient();
  const pattern = useQuery({
    ...patternQuery(patternId),
    refetchOnWindowFocus: false,
  });
  return (
    <QueryView query={pattern}>
      {(detail) => (
        <PatternView
          key={detail.pattern.id}
          detail={detail}
          onSave={async (patch) => {
            const saved = await patchPatternNotebook(patternId, patch);
            queryClient.setQueryData(keys.pattern(patternId), {
              ...detail,
              notebook: saved,
            });
            return saved;
          }}
          loadSaved={async () => (await getPattern(patternId)).notebook}
        />
      )}
    </QueryView>
  );
};
