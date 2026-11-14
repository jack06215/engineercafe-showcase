import { isApiError } from '@/api/client';
import type { TutorErrorKind } from '@/api/types';
import { TUTOR_ERROR_MESSAGE } from '@/common/format';

const KINDS = new Set(Object.keys(TUTOR_ERROR_MESSAGE));

// What an AI panel says when a call failed (SPEC §12.1): the kind's
// sentence, plus the server's message for plain errors.
export const tutorErrorText = (error: unknown): string => {
  if (
    isApiError(error, 'TUTOR_UNAVAILABLE') &&
    error.kind &&
    KINDS.has(error.kind)
  ) {
    const text = TUTOR_ERROR_MESSAGE[error.kind as TutorErrorKind];
    return error.kind === 'error' ? `${text} ${error.message}` : text;
  }
  return error instanceof Error ? error.message : String(error);
};

export const tutorKindText = (
  kind: TutorErrorKind | null,
  message: string | null,
): string => {
  const text = kind ? TUTOR_ERROR_MESSAGE[kind] : 'The report failed.';
  return message && (kind === 'error' || kind === null)
    ? `${text} ${message}`
    : text;
};
