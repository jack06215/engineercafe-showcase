import { useQuery, useQueryClient } from '@tanstack/react-query';

import { newIdempotencyKey } from '@/api/client';
import {
  patchSettings,
  postBackup,
  rebuildPlan,
  refreshBank,
  testTutor,
} from '@/api/endpoints';
import {
  backupQuery,
  bankQuery,
  keys,
  listsQuery,
  settingsQuery,
  tutorStatusQuery,
} from '@/api/queries';
import { QueryView } from '@/components/ui/QueryView';
import { deskQuery } from '@/features/desk/hooks/useDesk';
import { SettingsView } from '@/features/settings/components/SettingsView';

export const SettingsPage = () => {
  const queryClient = useQueryClient();
  const settings = useQuery(settingsQuery);
  const bank = useQuery(bankQuery);
  const lists = useQuery(listsQuery);
  const backup = useQuery(backupQuery);
  const tutor = useQuery(tutorStatusQuery);
  const desk = useQuery(deskQuery);
  const plan = desk.data?.plan ?? null;

  return (
    <QueryView query={settings}>
      {(data) => (
        <SettingsView
          settings={data}
          bank={bank.data ?? data.bank}
          lists={lists.data ?? []}
          backup={backup.data}
          tutor={tutor.data}
          onSave={async (patch) => {
            queryClient.setQueryData(keys.settings, await patchSettings(patch));
            void queryClient.invalidateQueries({ queryKey: keys.desk });
            void queryClient.invalidateQueries({ queryKey: keys.topics });
          }}
          onRefreshBank={async () => {
            queryClient.setQueryData(keys.bank, await refreshBank());
          }}
          onBackup={async () => {
            queryClient.setQueryData(keys.backup, await postBackup());
          }}
          onTestTutor={testTutor}
          onReplan={
            plan
              ? async () => {
                  await rebuildPlan(plan.id, plan.version, newIdempotencyKey());
                  await queryClient.invalidateQueries({ queryKey: keys.desk });
                }
              : null
          }
        />
      )}
    </QueryView>
  );
};
