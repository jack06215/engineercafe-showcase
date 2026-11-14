import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  activateList,
  createList,
  deactivateList,
  followBundled,
  importPack,
  previewList,
} from '@/api/endpoints';
import { keys, listsQuery } from '@/api/queries';
import { QueryView } from '@/components/ui/QueryView';
import { ListsView } from '@/features/lists/components/ListsView';

export const ListsPage = () => {
  const queryClient = useQueryClient();
  const lists = useQuery(listsQuery);
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: keys.lists });
    void queryClient.invalidateQueries({ queryKey: keys.settings });
    void queryClient.invalidateQueries({ queryKey: keys.desk });
  };
  const change = useMutation({
    mutationFn: (run: () => Promise<unknown>) => run(),
    onSettled: refresh,
  });

  return (
    <QueryView query={lists}>
      {(data) => (
        <ListsView
          lists={data}
          busy={change.isPending}
          onFollow={(set) => change.mutate(() => followBundled(set))}
          onToggleActive={(list) =>
            change.mutate(() =>
              list.active ? deactivateList(list.id) : activateList(list.id),
            )
          }
          onPreview={previewList}
          onCreate={async (body) => {
            const created = await createList(body);
            refresh();
            return created;
          }}
          onImport={async (pack, dryRun, key) => {
            const report = await importPack(pack, dryRun, key);
            if (!dryRun) refresh();
            return report;
          }}
        />
      )}
    </QueryView>
  );
};
