import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';

import type {
  ListCreated,
  ListEntriesIn,
  ListPreview,
  UnresolvedLine,
} from '@/api/types';
import { SOURCE_LABEL } from '@/common/format';

// Lines that resolved to nothing, and why; they're skipped.
export const Unresolved = ({ lines = [] }: { lines?: UnresolvedLine[] }) =>
  lines.length === 0 ? null : (
    <Alert severity="warning">
      Skipped {lines.length} {lines.length === 1 ? 'line' : 'lines'}:
      <List dense disablePadding>
        {lines.map(({ line, reason }) => (
          <ListItem key={line} disableGutters>
            <ListItemText primary={line} secondary={reason} />
          </ListItem>
        ))}
      </List>
    </Alert>
  );

type Props = {
  onPreview: (body: ListEntriesIn) => Promise<ListPreview>;
  onCreate: (body: ListEntriesIn) => Promise<ListCreated>;
};

// "Your own list" (SPEC §5.10): one entry per line, previewed before it's
// made. A paste mixing LeetCode and AtCoder becomes one list per source.
export const NewListForm = ({ onPreview, onCreate }: Props) => {
  const [name, setName] = useState('');
  const [text, setText] = useState('');
  const [preview, setPreview] = useState<ListPreview | null>(null);
  const [created, setCreated] = useState<ListCreated | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const body = { name: name.trim(), text };

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack spacing={1.5}>
      <TextField
        size="small"
        label="List name"
        value={name}
        onChange={(e) => {
          setName(e.target.value);
          setPreview(null);
        }}
      />
      <TextField
        multiline
        minRows={5}
        label="Entries, one per line"
        helperText="LeetCode links, slugs or exact titles; AtCoder task URLs. Up to 500."
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setPreview(null);
          setCreated(null);
        }}
      />
      <Stack direction="row" spacing={1}>
        <Button
          variant="outlined"
          disabled={busy || !body.name || !text.trim()}
          onClick={() =>
            void run(async () => setPreview(await onPreview(body)))
          }
        >
          Preview
        </Button>
        <Button
          variant="contained"
          disabled={busy || preview === null}
          onClick={() =>
            void run(async () => {
              setCreated(await onCreate(body));
              setPreview(null);
              setText('');
              setName('');
            })
          }
        >
          Create
        </Button>
      </Stack>
      {preview && (
        <Stack spacing={1} aria-label="Preview">
          {preview.groups.map((group) => (
            <div key={group.source}>
              <Typography variant="subtitle2">
                {group.name} ({SOURCE_LABEL[group.source]},{' '}
                {group.entries.length})
              </Typography>
              <List dense disablePadding>
                {group.entries.map((entry) => (
                  <ListItem key={entry.line} disableGutters>
                    <ListItemText
                      primary={entry.title}
                      secondary={
                        // `line` is the resolved slug or task id.
                        entry.problem_id
                          ? entry.line
                          : `${entry.line} · new to the library`
                      }
                    />
                  </ListItem>
                ))}
              </List>
            </div>
          ))}
          <Unresolved lines={preview.unresolved_reasons} />
        </Stack>
      )}
      {created && (
        <Alert severity="success">
          Created {created.lists.map((l) => l.name).join(' and ')}.
        </Alert>
      )}
      {created && <Unresolved lines={created.unresolved_reasons} />}
      {error && <Alert severity="error">{error}</Alert>}
    </Stack>
  );
};
