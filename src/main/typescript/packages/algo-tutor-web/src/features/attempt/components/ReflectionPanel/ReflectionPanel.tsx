import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormGroup from '@mui/material/FormGroup';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';

import type { MistakeLabel } from '@/api/types';
import { MISTAKE_LABEL } from '@/common/format';
import { useBeforeUnloadGuard } from '@/hooks';

type Props = {
  labels: MistakeLabel[];
  takeaway: string;
  onSave: (labels: MistakeLabel[], takeaway: string) => Promise<void>;
};

const LABELS = Object.keys(MISTAKE_LABEL) as MistakeLabel[];

// "What will you remember?" (SPEC §6.7): up to three mistake labels and a
// one-sentence takeaway, saved on their own. They feed the mistake notebook.
export const ReflectionPanel = ({ labels, takeaway, onSave }: Props) => {
  const [chosen, setChosen] = useState<MistakeLabel[]>(labels);
  const [text, setText] = useState(takeaway);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const dirty =
    text !== takeaway ||
    chosen.length !== labels.length ||
    chosen.some((l) => !labels.includes(l));
  useBeforeUnloadGuard(dirty);

  const toggle = (label: MistakeLabel) => {
    setSaved(false);
    setChosen((current) =>
      current.includes(label)
        ? current.filter((l) => l !== label)
        : [...current, label],
    );
  };

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await onSave(chosen, text);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack spacing={1.5} component="section" aria-label="Reflection">
      <Typography variant="h6" component="h2">
        What will you remember?
      </Typography>
      <FormGroup row>
        {LABELS.map((label) => (
          <FormControlLabel
            key={label}
            control={
              <Checkbox
                size="small"
                checked={chosen.includes(label)}
                onChange={() => toggle(label)}
              />
            }
            label={MISTAKE_LABEL[label]}
          />
        ))}
      </FormGroup>
      <TextField
        label="One-sentence takeaway"
        size="small"
        multiline
        value={text}
        onChange={(e) => {
          setSaved(false);
          setText(e.target.value);
        }}
        slotProps={{ htmlInput: { maxLength: 2000 } }}
        helperText={`${text.length} / 2000`}
      />
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <Button
          variant="outlined"
          onClick={() => void save()}
          disabled={busy || !dirty}
        >
          Save reflection
        </Button>
        {saved && !dirty && (
          <Typography variant="body2" color="text.secondary" role="status">
            Saved
          </Typography>
        )}
      </Stack>
      {error && <Alert severity="error">{error}</Alert>}
    </Stack>
  );
};
