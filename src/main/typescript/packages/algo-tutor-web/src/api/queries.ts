// TanStack Query options per GET, so screens and tests share the keys.
import { queryOptions } from '@tanstack/react-query';

import * as endpoints from './endpoints';

import type { ProblemFilters } from './endpoints';

export const keys = {
  setup: ['setup'] as const,
  settings: ['settings'] as const,
  desk: ['desk'] as const,
  problems: (filters: ProblemFilters) => ['problems', filters] as const,
  problem: (id: string) => ['problem', id] as const,
  attempt: (id: string) => ['attempt', id] as const,
  hints: (id: string) => ['attempt', id, 'hints'] as const,
  lists: ['lists'] as const,
  list: (id: string) => ['list', id] as const,
  bank: ['bank'] as const,
  topics: ['topics'] as const,
  topic: (id: string) => ['topic', id] as const,
  patterns: ['patterns'] as const,
  pattern: (id: string) => ['pattern', id] as const,
  mistakes: ['mistakes'] as const,
  tutor: ['tutor'] as const,
  backup: ['backup'] as const,
};

export const setupQuery = queryOptions({
  queryKey: keys.setup,
  queryFn: endpoints.getSetup,
});
export const settingsQuery = queryOptions({
  queryKey: keys.settings,
  queryFn: endpoints.getSettings,
});
export const problemsQuery = (filters: ProblemFilters) =>
  queryOptions({
    queryKey: keys.problems(filters),
    queryFn: () => endpoints.getProblems(filters),
  });
export const problemQuery = (id: string) =>
  queryOptions({
    queryKey: keys.problem(id),
    queryFn: () => endpoints.getProblem(id),
  });
export const attemptQuery = (id: string) =>
  queryOptions({
    queryKey: keys.attempt(id),
    queryFn: () => endpoints.getAttempt(id),
  });
export const hintsQuery = (id: string) =>
  queryOptions({
    queryKey: keys.hints(id),
    queryFn: () => endpoints.getHints(id),
  });
export const listsQuery = queryOptions({
  queryKey: keys.lists,
  queryFn: endpoints.getLists,
});
export const listQuery = (id: string) =>
  queryOptions({
    queryKey: keys.list(id),
    queryFn: () => endpoints.getList(id),
  });
export const bankQuery = queryOptions({
  queryKey: keys.bank,
  queryFn: endpoints.getBank,
  // SPEC §5.4: polled every 2 s while a download runs.
  refetchInterval: (query) =>
    query.state.data?.status === 'running' ? 2000 : false,
});
export const topicsQuery = queryOptions({
  queryKey: keys.topics,
  queryFn: endpoints.getTopics,
});
export const topicQuery = (id: string) =>
  queryOptions({
    queryKey: keys.topic(id),
    queryFn: () => endpoints.getTopic(id),
  });
export const patternsQuery = queryOptions({
  queryKey: keys.patterns,
  queryFn: endpoints.getPatterns,
});
export const patternQuery = (id: string) =>
  queryOptions({
    queryKey: keys.pattern(id),
    queryFn: () => endpoints.getPattern(id),
  });
export const mistakesQuery = queryOptions({
  queryKey: keys.mistakes,
  queryFn: endpoints.getMistakes,
});
export const tutorStatusQuery = queryOptions({
  queryKey: keys.tutor,
  queryFn: endpoints.getTutorStatus,
});
export const backupQuery = queryOptions({
  queryKey: keys.backup,
  queryFn: endpoints.getBackup,
});
