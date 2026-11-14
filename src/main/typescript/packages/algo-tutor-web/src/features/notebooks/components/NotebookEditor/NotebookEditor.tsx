import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useEffect, useState } from 'react';

import { isApiError } from '@/api/client';
import type { Notebook, NotebookPatch } from '@/api/types';
import { formatTimestamp } from '@/common/format';
import { useLeaveGuard } from '@/hooks';

import {
  clearRecovery,
  type NotebookText,
  readRecovery,
  writeRecovery,
} from './recovery';

type Props = {
  notebook: Notebook;
  // Names this notebook's recovery draft ("topic:hash-table").
  storageKey: string;
  onSave: (patch: NotebookPatch) => Promise<Notebook>;
  // The saved copy, for "Refresh saved version, keep my changes".
  loadSaved: () => Promise<Notebook>;
};

const FIELDS: { field: keyof NotebookText; label: string; hint: string }[] = [
  {
    field: 'cues',
    label: 'Recognition cues',
    hint: 'What in a problem statement points here?',
  },
  {
    field: 'pitfalls',
    label: 'Common pitfalls',
    hint: 'What goes wrong when you apply it?',
  },
  { field: 'notes', label: 'Notes', hint: 'Anything else, in your own words.' },
];

const textOf = (n: Notebook): NotebookText => ({
  cues: n.cues,
  pitfalls: n.pitfalls,
  notes: n.notes,
});

const same = (a: NotebookText, b: NotebookText) =>
  a.cues === b.cues && a.pitfalls === b.pitfalls && a.notes === b.notes;

// A notebook's three fields (SPEC §11): versioned saves, a local recovery
// draft, and a guard against leaving with unsaved changes.
export const NotebookEditor = ({
  notebook,
  storageKey,
  onSave,
  loadSaved,
}: Props) => {
  const [saved, setSaved] = useState(notebook);
  const [text, setText] = useState<NotebookText>(() => textOf(notebook));
  const [recovery, setRecovery] = useState<NotebookText | null>(() => {
    const draft = readRecovery(storageKey);
    return draft && !same(draft, textOf(notebook)) ? draft : null;
  });
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = !same(text, textOf(saved));
  useLeaveGuard(dirty);

  useEffect(() => {
    if (dirty) writeRecovery(storageKey, text);
  }, [dirty, storageKey, text]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await onSave({ version: saved.version, ...text });
      setSaved(next);
      setStale(false);
      clearRecovery(storageKey);
    } catch (e) {
      if (isApiError(e, 'STALE')) setStale(true);
      else setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  // Take the server's copy as the saved one, keep the text on screen; the
  // next save overwrites what changed elsewhere.
  const refreshKeepingChanges = async () => {
    try {
      setSaved(await loadSaved());
      setStale(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <Stack spacing={2} component="section" aria-label="Your notebook">
      <Typography variant="h6" component="h2">
        Your notebook
      </Typography>
      {recovery && (
        <Alert
          severity="info"
          action={
            <Stack direction="row" spacing={1}>
              <Button
                color="inherit"
                size="small"
                onClick={() => {
                  setText(recovery);
                  setRecovery(null);
                }}
              >
                Restore
              </Button>
              <Button
                color="inherit"
                size="small"
                onClick={() => {
                  clearRecovery(storageKey);
                  setRecovery(null);
                }}
              >
                Discard
              </Button>
            </Stack>
          }
        >
          This browser kept changes you didn't save last time.
        </Alert>
      )}
      {FIELDS.map(({ field, label, hint }) => (
        <TextField
          key={field}
          label={label}
          helperText={hint}
          multiline
          minRows={3}
          value={text[field]}
          onChange={(e) => setText((t) => ({ ...t, [field]: e.target.value }))}
          slotProps={{ htmlInput: { maxLength: 1_000_000 } }}
        />
      ))}
      {stale && (
        <Alert
          severity="warning"
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => void refreshKeepingChanges()}
            >
              Refresh saved version, keep my changes
            </Button>
          }
        >
          This notebook changed elsewhere since you opened it.
        </Alert>
      )}
      {error && <Alert severity="error">{error}</Alert>}
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
        <Button
          variant="contained"
          onClick={() => void save()}
          disabled={busy || !dirty || stale}
        >
          Save notebook
        </Button>
        <Typography variant="body2" color="text.secondary" role="status">
          {dirty
            ? 'Unsaved changes'
            : saved.updated_at
              ? `Saved ${formatTimestamp(saved.updated_at)}`
              : 'Nothing written yet'}
        </Typography>
      </Stack>
    </Stack>
  );
};
