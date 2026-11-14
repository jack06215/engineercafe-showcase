// How the app words the contract's values.
import { format, parseISO } from 'date-fns';

import type {
  Help,
  MistakeLabel,
  Outcome,
  Result,
  ReviewAction,
  ReviewStage,
  Source,
  TutorErrorKind,
} from '@/api/types';

export const OUTCOME_LABEL: Record<Outcome, string> = {
  solved: 'Solved',
  not_solved: 'Not solved',
  stopped: 'Stopped',
};

export const HELP_LABEL: Record<Help, string> = {
  unknown: 'Unknown',
  none: 'None',
  small: 'Small hint',
  major: 'Major help',
  solution: 'Solution viewed',
};

export const MISTAKE_LABEL: Record<MistakeLabel, string> = {
  missed_edge_case: 'Missed edge case',
  wrong_approach: 'Wrong approach',
  implementation_bug: 'Implementation bug',
};

export const RESULT_LABEL: Record<Result, string> = {
  strong: 'strong',
  ok: 'OK',
  struggled: 'struggled',
};

export const REVIEW_ACTION_LABEL: Record<ReviewAction, string> = {
  recommended: 'Recommended date',
  manual: 'A date you chose',
  snooze: 'Snoozed',
  none: 'No scheduled review',
};

export const REVIEW_STAGE_LABEL: Record<ReviewStage, string> = {
  repair: 'Repair',
  reconstruction: 'Reconstruction',
  transfer: 'Transfer',
  mixed: 'Mixed',
  retired: 'Retired',
  covered: 'Covered by a check',
  snoozed: 'Snoozed',
};

export const SOURCE_LABEL: Record<Source, string> = {
  leetcode: 'LeetCode',
  atcoder: 'AtCoder',
};

export const LANGUAGE_LABEL = {
  python: 'Python',
  go: 'Go',
  typescript: 'TypeScript',
} as const;

// SPEC §12.1: why an AI panel has nothing to show.
export const TUTOR_ERROR_MESSAGE: Record<TutorErrorKind, string> = {
  disabled: 'Algo-chan is off: tutor.enabled is false in config.yaml.',
  unavailable: "Can't reach the model. Is Ollama running?",
  model_missing:
    "The configured model isn't installed. Pull it, or change config.yaml.",
  timeout: 'Algo-chan took too long to answer.',
  invalid_output:
    "Algo-chan's answer didn't fit the expected shape, even after one repair.",
  error: 'Algo-chan ran into an error.',
};

// "2026-11-08" → "Sun 8 Nov 2026".
export const formatDay = (isoDate: string): string =>
  format(parseISO(isoDate), 'EEE d MMM yyyy');

// An ISO timestamp in local time: "8 Nov 2026, 14:05".
export const formatTimestamp = (iso: string): string =>
  format(parseISO(iso), 'd MMM yyyy, HH:mm');

// Today's date as YYYY-MM-DD in local time, for date inputs' min values.
export const localIsoDate = (date: Date): string => format(date, 'yyyy-MM-dd');

// SPEC §1.2 of BloomCode: the greeting by local hour.
export const greeting = (hour: number): string =>
  hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
