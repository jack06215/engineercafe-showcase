import {
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { useState } from 'react';

import { isApiError, newIdempotencyKey } from '@/api/client';
import * as endpoints from '@/api/endpoints';
import { keys } from '@/api/queries';
import type { Desk, Lane, PlanItemOut } from '@/api/types';

import type { DeskActions } from '../components/DeskView';

// SPEC §10.1: plans are made lazily, when the desk loads. Ensuring on every
// fetch also rolls the desk over at midnight.
export const deskQuery = queryOptions({
  queryKey: keys.desk,
  queryFn: async (): Promise<Desk> => {
    try {
      await endpoints.ensureToday();
    } catch (error) {
      // The desk itself says when an assessment hides the plan.
      if (!isApiError(error, 'HIDDEN_ASSESSMENT')) throw error;
    }
    return endpoints.getDesk();
  },
  refetchInterval: 60_000,
});

const messageFor = (error: unknown): string => {
  if (isApiError(error, 'NO_REPLACEMENT')) {
    return 'No other question fits your current training levels.';
  }
  if (isApiError(error, 'STALE')) {
    return 'The plan changed elsewhere, so it was reloaded. Try again.';
  }
  if (isApiError(error, 'ACTIVE_ATTEMPT')) {
    return 'Finish or cancel the attempt in progress first.';
  }
  return error instanceof Error ? error.message : String(error);
};

// The desk's data and every action on it. Each action refetches the desk,
// whose plan version the next action needs.
export const useDesk = () => {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const desk = useQuery(deskQuery);
  const [message, setMessage] = useState<string | null>(null);
  const [busyItemId, setBusyItemId] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async ({
      run,
    }: {
      item: PlanItemOut | null;
      run: () => Promise<unknown>;
    }) => run(),
    onMutate: ({ item }) => {
      setMessage(null);
      setBusyItemId(item?.id ?? null);
    },
    onError: (error) => setMessage(messageFor(error)),
    onSettled: () => {
      setBusyItemId(null);
      return queryClient.invalidateQueries({ queryKey: keys.desk });
    },
  });

  const plan = desk.data?.plan ?? null;
  const act = (item: PlanItemOut | null, run: () => Promise<unknown>) =>
    mutation.mutate({ item, run });
  const withPlan =
    (
      fn: (
        planId: string,
        version: number,
        item: PlanItemOut,
      ) => Promise<unknown>,
    ) =>
    (item: PlanItemOut) => {
      if (plan) act(item, () => fn(plan.id, plan.version, item));
    };

  const openAttempt = (attemptId: string) =>
    navigate({ to: '/attempts/$id', params: { id: attemptId } });

  const laneOrder = (lane: Lane) =>
    (plan?.items ?? [])
      .filter((i) => i.lane === lane)
      .sort((a, b) => a.position - b.position);

  const actions: DeskActions = {
    start: (item) =>
      act(item, async () => {
        const started = await endpoints.startAttempt({
          problem_id: item.problem.id,
          plan_item_id: item.id,
          language: 'python',
        });
        await openAttempt(started.id);
      }),
    resume: (item) => {
      if (item.attempt_id) void openAttempt(item.attempt_id);
    },
    resumeAttempt: (attemptId) => void openAttempt(attemptId),
    makeNext: withPlan((planId, version, item) =>
      endpoints.activateItem(planId, item.id, version),
    ),
    replace: withPlan((planId, version, item) =>
      endpoints.disposeItem(planId, item.id, { version, action: 'swap' }),
    ),
    postpone: (item, until) =>
      withPlan((planId, version) =>
        endpoints.disposeItem(planId, item.id, {
          version,
          action: 'snooze',
          snooze_until: until,
        }),
      )(item),
    skip: withPlan((planId, version, item) =>
      endpoints.disposeItem(planId, item.id, { version, action: 'skip' }),
    ),
    move: (item, by) =>
      withPlan((planId, version) => {
        // Every item of the lane, once, with this one moved past its
        // neighbour among the unfinished ones.
        const lane = laneOrder(item.lane);
        const ids = lane.map((i) => i.id);
        const from = ids.indexOf(item.id);
        const movable = lane.filter(
          (i) => i.status !== 'completed' && i.status !== 'skipped',
        );
        const neighbour = movable[movable.indexOf(item) + by];
        if (!neighbour) return Promise.resolve();
        const to = ids.indexOf(neighbour.id);
        ids.splice(from, 1);
        ids.splice(to, 0, item.id);
        return endpoints.reorderLane(planId, {
          version,
          lane: item.lane,
          item_ids: ids,
        });
      })(item),
    cancel: (item) => {
      const attemptId = item.attempt_id;
      if (!attemptId) return;
      if (
        !window.confirm('Cancel this attempt? Its code and notes are deleted.')
      ) {
        return;
      }
      act(item, () => endpoints.cancelAttempt(attemptId));
    },
    signal: (item, feel) => {
      const attemptId = item.attempt_id;
      if (attemptId) {
        act(item, () =>
          endpoints.patchSignals(attemptId, { difficulty: feel }),
        );
      }
    },
    replan: () => {
      if (plan) {
        act(null, () =>
          endpoints.rebuildPlan(plan.id, plan.version, newIdempotencyKey()),
        );
      }
    },
  };

  return {
    desk,
    actions,
    message,
    clearMessage: () => setMessage(null),
    busyItemId,
    replanning: mutation.isPending && busyItemId === null,
  };
};
