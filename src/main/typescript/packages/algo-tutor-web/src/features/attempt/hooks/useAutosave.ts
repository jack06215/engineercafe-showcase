import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';

import { isApiError } from '@/api/client';

import type { Versioned, VersionedLane } from '../common/lane';

// SPEC §6.5: saved 650 ms after the last edit.
export const AUTOSAVE_DELAY_MS = 650;

export type SaveStatus = 'saved' | 'dirty' | 'saving' | 'error';

export const SAVE_STATUS_LABEL: Record<SaveStatus, string> = {
  saved: 'Saved',
  dirty: 'Unsaved changes',
  saving: 'Saving…',
  error: 'Not saved',
};

type Options<R extends Versioned, D> = {
  lane: VersionedLane<R>;
  // The draft fields as the record has them saved.
  draftOf: (record: R) => D;
  sameDraft: (a: D, b: D) => boolean;
  // Write `draft` with `record.version`; resolve to the server's copy.
  save: (record: R, draft: D) => Promise<R>;
  // False once the record takes no more drafts (a completed attempt).
  enabled?: boolean;
  delayMs?: number;
};

// Autosave for a draft held in memory over a versioned record (SPEC §6.5).
//
// Edits are debounced, then saved through the record's lane, so a save never
// overlaps another write and always carries the latest version. The draft is
// read when the save actually runs, not when it was scheduled, so it always
// sends the latest text. A failure freezes saving and keeps the edits in
// memory: `stale` (409 STALE) means the record changed elsewhere; offer
// "Copy unsaved text" and `reload`. Anything else can be `retry`'d.
export const useAutosave = <R extends Versioned, D>({
  lane,
  draftOf,
  sameDraft,
  save,
  enabled = true,
  delayMs = AUTOSAVE_DELAY_MS,
}: Options<R, D>) => {
  const { record, error } = useSyncExternalStore(
    lane.subscribe,
    lane.getSnapshot,
    lane.getSnapshot,
  );
  const [draft, setDraft] = useState<D>(() => draftOf(record));
  const draftRef = useRef(draft);
  const [pending, setPending] = useState(0);

  // The callbacks run outside render, so they read the latest options here.
  const latestRef = useRef({ draftOf, sameDraft, save });
  useEffect(() => {
    latestRef.current = { draftOf, sameDraft, save };
  });

  const changeDraft = useCallback((update: D | ((current: D) => D)) => {
    const next =
      typeof update === 'function'
        ? (update as (current: D) => D)(draftRef.current)
        : update;
    draftRef.current = next;
    setDraft(next);
  }, []);

  const saveNow = useCallback(async () => {
    setPending((n) => n + 1);
    try {
      await lane.run((current) => {
        const { draftOf, sameDraft, save } = latestRef.current;
        const snapshot = draftRef.current;
        return sameDraft(draftOf(current), snapshot)
          ? Promise.resolve(current)
          : save(current, snapshot);
      });
    } catch {
      // The lane keeps the error; the status shows it and edits stay.
    } finally {
      setPending((n) => n - 1);
    }
  }, [lane]);

  const dirty = !sameDraft(draftOf(record), draft);

  useEffect(() => {
    if (!enabled || error || !dirty) return;
    const id = window.setTimeout(() => void saveNow(), delayMs);
    return () => window.clearTimeout(id);
  }, [draft, record, enabled, error, dirty, delayMs, saveNow]);

  // Save now if anything is unsaved (before leaving or finishing).
  const flush = useCallback(async () => {
    const { draftOf, sameDraft } = latestRef.current;
    if (!lane.error && !sameDraft(draftOf(lane.record), draftRef.current)) {
      await saveNow();
    }
    await lane.run(async (current) => current).catch(() => undefined);
  }, [lane, saveNow]);

  const retry = useCallback(async () => {
    lane.clearError();
    await saveNow();
  }, [lane, saveNow]);

  // "Reload saved version": take the server's copy, dropping local edits.
  const reload = useCallback(
    async (fetchLatest: () => Promise<R>) => {
      const saved = await fetchLatest();
      lane.replace(saved);
      changeDraft(latestRef.current.draftOf(saved));
    },
    [lane, changeDraft],
  );

  const status: SaveStatus = error
    ? 'error'
    : pending > 0
      ? 'saving'
      : dirty
        ? 'dirty'
        : 'saved';

  return {
    record,
    draft,
    setDraft: changeDraft,
    status,
    statusLabel: SAVE_STATUS_LABEL[status],
    // Something isn't on the server yet: guard leaving the page.
    unsaved: status !== 'saved',
    error,
    stale: isApiError(error, 'STALE'),
    flush,
    retry,
    reload,
  };
};
