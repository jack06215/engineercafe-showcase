import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';

import {
  activateList,
  deactivateList,
  deleteList,
  patchList,
} from '@/api/endpoints';
import { keys, listQuery } from '@/api/queries';
import { QueryView } from '@/components/ui/QueryView';
import { ListView } from '@/features/lists/components/ListView';

type Props = { listId: string };

export const ListPage = ({ listId }: Props) => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const list = useQuery(listQuery(listId));
  const refreshOthers = () => {
    void queryClient.invalidateQueries({ queryKey: keys.lists });
    void queryClient.invalidateQueries({ queryKey: keys.desk });
  };

  return (
    <QueryView query={list}>
      {(detail) => (
        <ListView
          key={detail.summary.id}
          detail={detail}
          onPatch={async (patch) => {
            queryClient.setQueryData(
              keys.list(listId),
              await patchList(listId, patch),
            );
            refreshOthers();
          }}
          onToggleActive={async () => {
            await (detail.summary.active
              ? deactivateList(listId)
              : activateList(listId));
            await queryClient.invalidateQueries({
              queryKey: keys.list(listId),
            });
            refreshOthers();
          }}
          onDelete={async () => {
            await deleteList(listId);
            refreshOthers();
            await navigate({ to: '/lists' });
          }}
        />
      )}
    </QueryView>
  );
};
