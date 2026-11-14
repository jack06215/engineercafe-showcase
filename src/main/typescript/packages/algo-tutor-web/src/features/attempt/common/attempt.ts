// How the attempt page maps AttemptOut onto the write lane's hooks.
import { isApiError } from '@/api/client';
import { patchDraft, postTimer } from '@/api/endpoints';
import type { AttemptOut, Language } from '@/api/types';

import type { TimerAction, TimerState } from '../hooks/useStopwatch';

// What autosave holds in memory. With a linked file (SPEC §6.4) the code
// comes from the file, so only the notes and language are drafts.
export type AttemptDraft = {
  code: string;
  notes: string;
  language: Language;
  linked: boolean;
};

export const draftOf = (attempt: AttemptOut): AttemptDraft => ({
  code: attempt.code,
  notes: attempt.notes,
  language: attempt.language,
  linked: attempt.solution_path !== null,
});

// `saved` is the record's side: a linked attempt's code isn't compared.
export const sameDraft = (saved: AttemptDraft, draft: AttemptDraft) =>
  saved.notes === draft.notes &&
  saved.language === draft.language &&
  (saved.linked || saved.code === draft.code);

// Sends only what changed, so a save never writes back notes the server
// changed meanwhile (hints append to them). With a linked file the server
// copies it at every draft save (SPEC §6.4) from the solution_path it holds,
// skipping a file that has vanished, so the client never sends its code.
export const saveDraft = (attempt: AttemptOut, draft: AttemptDraft) =>
  patchDraft(attempt.id, {
    version: attempt.version,
    ...(draft.notes !== attempt.notes ? { notes: draft.notes } : {}),
    ...(draft.language !== attempt.language
      ? { language: draft.language }
      : {}),
    ...(attempt.solution_path === null && draft.code !== attempt.code
      ? { code: draft.code }
      : {}),
  });

export const timerOf = (attempt: AttemptOut): TimerState => ({
  status: attempt.status,
  activeSeconds: attempt.active_seconds,
  lastHeartbeatAt: attempt.last_heartbeat_at,
  serverNow: attempt.server_now,
  needsGapDecision: attempt.needs_gap_decision,
  gapSeconds: attempt.gap_seconds,
});

export const sendTimer = (
  attempt: AttemptOut,
  action: TimerAction,
  includeGap?: boolean,
) =>
  postTimer(attempt.id, {
    version: attempt.version,
    action,
    ...(includeGap === undefined ? {} : { include_gap: includeGap }),
  });

// Failures that are about the request, not the record: they're shown where
// they happened and don't freeze the attempt's writes.
const SOFT_CODES = new Set([
  'SOLUTION_FILE_MISSING',
  'SOLUTION_PATH_INVALID',
  'VALIDATION',
  'TUTOR_UNAVAILABLE',
  'GAP_DECISION',
]);
export const isSoftError = (error: unknown) =>
  isApiError(error) && SOFT_CODES.has(error.code);

export const sourceName = (attempt: AttemptOut) =>
  attempt.problem.source === 'atcoder' ? 'AtCoder' : 'LeetCode';
