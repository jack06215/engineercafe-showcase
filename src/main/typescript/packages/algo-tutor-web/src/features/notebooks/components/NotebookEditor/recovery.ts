// The notebook's local recovery draft (SPEC §11), per browser. Storage can
// be missing or refuse writes (private windows, blocked site data), so every
// call is guarded and a failure just means no recovery draft.

export type NotebookText = { cues: string; pitfalls: string; notes: string };

const PREFIX = 'algo-tutor.notebook-draft.';

export const readRecovery = (key: string): NotebookText | null => {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (
      value &&
      typeof value === 'object' &&
      ['cues', 'pitfalls', 'notes'].every(
        (f) => typeof (value as Record<string, unknown>)[f] === 'string',
      )
    ) {
      return value as NotebookText;
    }
  } catch {
    // No storage, or not ours.
  }
  return null;
};

export const writeRecovery = (key: string, text: NotebookText): void => {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(text));
  } catch {
    // No storage: nothing to recover later.
  }
};

export const clearRecovery = (key: string): void => {
  try {
    window.localStorage.removeItem(PREFIX + key);
  } catch {
    // No storage.
  }
};
