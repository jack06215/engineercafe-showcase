import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';

import { isApiError, newIdempotencyKey } from '@/api/client';
import {
  finishAttempt,
  getAttempt,
  patchDraft,
  postHint,
} from '@/api/endpoints';
import { hintsQuery, keys, tutorStatusQuery } from '@/api/queries';
import type { AttemptOut, Language } from '@/api/types';
import { LANGUAGE_LABEL, TUTOR_ERROR_MESSAGE } from '@/common/format';
import { useBeforeUnloadGuard } from '@/hooks';

import {
  draftOf,
  isSoftError,
  sameDraft,
  saveDraft,
  sendTimer,
  timerOf,
} from '../../common/attempt';
import { runSoft, type VersionedLane } from '../../common/lane';
import { useAutosave } from '../../hooks/useAutosave';
import { useStopwatch } from '../../hooks/useStopwatch';
import { FinishForm, type FinishValues } from '../FinishForm';
import { HintPanel } from '../HintPanel';
import { SaveStatus } from '../SaveStatus';
import { SolutionSource } from '../SolutionSource';
import { StaleNotice } from '../StaleNotice';
import { Stopwatch } from '../Stopwatch';

const LANGUAGES = Object.keys(LANGUAGE_LABEL) as Language[];

type Props = {
  lane: VersionedLane<AttemptOut>;
};

// An unfinished attempt (SPEC §6.2–§6.6, §12.5): the stopwatch, the code
// (a linked file or the editor), notes with autosave, hints and the result
// form. Every write goes through the attempt's lane.
export const ActiveAttempt = ({ lane }: Props) => {
  const queryClient = useQueryClient();
  const [hintPending, setHintPending] = useState(false);
  const autosave = useAutosave({
    lane,
    draftOf,
    sameDraft,
    save: saveDraft,
    // A hint appends to the notes on the server; hold drafts until it lands.
    enabled: !hintPending,
  });
  const stopwatch = useStopwatch({ lane, timerOf, send: sendTimer });
  const { record, draft, setDraft } = autosave;
  useBeforeUnloadGuard(autosave.unsaved);

  const hints = useQuery(hintsQuery(record.id));
  const tutor = useQuery(tutorStatusQuery);
  const lastFinishRef = useRef<{ key: string; body: string } | null>(null);
  const frozen = autosave.error !== null;

  const link = async (path: string) => {
    await autosave.flush();
    const saved = await runSoft(
      lane,
      (r) => patchDraft(r.id, { version: r.version, solution_path: path }),
      isSoftError,
    );
    setDraft((d) => ({ ...d, linked: true, code: saved.code }));
  };

  const unlink = async () => {
    await autosave.flush();
    const saved = await runSoft(
      lane,
      (r) => patchDraft(r.id, { version: r.version, solution_path: null }),
      isSoftError,
    );
    setDraft((d) => ({ ...d, linked: false, code: saved.code }));
  };

  const sendHint = async (text: string) => {
    await autosave.flush();
    setHintPending(true);
    try {
      // The hint call carries no version (it may take 90 s; heartbeats go on
      // meanwhile). Adopt its notes and version unless a later write already
      // brought them.
      const reply = await postHint(record.id, text);
      const merged = await lane.run(async (r) =>
        reply.attempt_version > r.version
          ? {
              ...r,
              version: reply.attempt_version,
              notes: reply.notes,
              strongest_hint: reply.strongest_level,
            }
          : { ...r, strongest_hint: reply.strongest_level },
      );
      setDraft((d) => ({ ...d, notes: merged.notes }));
    } finally {
      setHintPending(false);
      void queryClient.invalidateQueries({ queryKey: keys.hints(record.id) });
    }
  };

  const finish = async (values: FinishValues) => {
    await autosave.flush();
    if (lane.error) {
      throw new Error("Your latest edits aren't saved; sort that out first.");
    }
    const extra = {
      language: draft.language,
      notes: draft.notes,
      ...(record.solution_path === null ? { code: draft.code } : {}),
    };
    // The same body again (a retry after a lost response) reuses its key,
    // so the server replays the first result instead of finishing twice.
    const body = JSON.stringify({ ...values, ...extra });
    const key =
      lastFinishRef.current?.body === body
        ? lastFinishRef.current.key
        : newIdempotencyKey();
    lastFinishRef.current = { key, body };
    try {
      await runSoft(
        lane,
        async (r) =>
          (
            await finishAttempt(
              r.id,
              { version: r.version, ...values, ...extra },
              key,
            )
          ).attempt,
        isSoftError,
      );
    } catch (e) {
      // Draft saves skip a vanished file; finishing is where it shows.
      if (isApiError(e, 'SOLUTION_FILE_MISSING')) {
        throw new Error(
          `${record.solution_path} is missing. Fix the path or switch to the editor, then save again.`,
          { cause: e },
        );
      }
      throw e;
    }
    void queryClient.invalidateQueries({ queryKey: keys.desk });
  };

  const tutorOff =
    tutor.data && !tutor.data.enabled ? TUTOR_ERROR_MESSAGE.disabled : null;
  const hasCode = record.solution_path !== null || draft.code.trim() !== '';

  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, lg: 8 }}>
        <Stack spacing={2}>
          {autosave.stale && (
            <StaleNotice
              unsavedText={`${draft.code}\n\n${draft.notes}`}
              onReload={() => void autosave.reload(() => getAttempt(record.id))}
            />
          )}
          {frozen && !autosave.stale && (
            <Alert
              severity="error"
              action={
                <Button
                  color="inherit"
                  size="small"
                  onClick={() => void autosave.retry()}
                >
                  Retry
                </Button>
              }
            >
              Not saved:{' '}
              {autosave.error instanceof Error
                ? autosave.error.message
                : String(autosave.error)}
            </Alert>
          )}
          <Stack
            direction="row"
            spacing={2}
            sx={{ alignItems: 'center', justifyContent: 'space-between' }}
          >
            <TextField
              select
              size="small"
              label="Language"
              value={draft.language}
              onChange={(e) =>
                setDraft((d) => ({
                  ...d,
                  language: e.target.value as Language,
                }))
              }
              sx={{ minWidth: 160 }}
            >
              {LANGUAGES.map((l) => (
                <MenuItem key={l} value={l}>
                  {LANGUAGE_LABEL[l]}
                </MenuItem>
              ))}
            </TextField>
            <SaveStatus status={autosave.status} />
          </Stack>
          <SolutionSource
            attempt={record}
            code={draft.code}
            language={draft.language}
            onCodeChange={(code) => setDraft((d) => ({ ...d, code }))}
            onLink={link}
            onUnlink={unlink}
            disabled={frozen}
          />
          <TextField
            label="Notes"
            placeholder="Approach, mistakes, or a submission link"
            multiline
            minRows={4}
            value={draft.notes}
            onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
            disabled={hintPending}
            helperText={hintPending ? 'Algo-chan is adding a hint here…' : ' '}
          />
        </Stack>
      </Grid>
      <Grid size={{ xs: 12, lg: 4 }}>
        <Stack spacing={2}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stopwatch
              seconds={stopwatch.seconds}
              running={stopwatch.running}
              paused={stopwatch.paused}
              gapPending={stopwatch.gapPending}
              gapSeconds={stopwatch.gapSeconds}
              onPause={() => void stopwatch.pause().catch(() => undefined)}
              onResume={(includeGap) =>
                void stopwatch.resume(includeGap).catch(() => undefined)
              }
              disabled={frozen}
            />
          </Paper>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <HintPanel
              messages={hints.data?.messages ?? []}
              onSend={sendHint}
              unavailable={tutorOff}
              disabled={frozen}
            />
          </Paper>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <FinishForm
              stopwatchSeconds={stopwatch.seconds}
              strongestHint={record.strongest_hint}
              hasCode={hasCode}
              onSubmit={finish}
              disabled={frozen || hintPending}
            />
          </Paper>
        </Stack>
      </Grid>
    </Grid>
  );
};
