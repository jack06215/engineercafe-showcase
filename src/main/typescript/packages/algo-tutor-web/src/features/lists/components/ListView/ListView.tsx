import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import IconButton from '@mui/material/IconButton';
import Link from '@mui/material/Link';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import ListSubheader from '@mui/material/ListSubheader';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { createLink } from '@tanstack/react-router';
import { useState } from 'react';

import type { ListDetail, ListEntryOut, ListPatch } from '@/api/types';
import { SOURCE_LABEL } from '@/common/format';
import { RatingChip } from '@/components/ui/RatingChip';

import { Unresolved } from '../NewListForm';

const RouterLink = createLink(Link);

type Props = {
  detail: ListDetail;
  onPatch: (patch: ListPatch) => Promise<void>;
  onToggleActive: () => Promise<void>;
  onDelete: () => Promise<void>;
};

// One list (SPEC §5.10, §14 Lists): its entries in order, with progress.
// Your own lists can be renamed, reordered, added to and trimmed; bundled
// and pack lists are read-only.
export const ListView = ({
  detail,
  onPatch,
  onToggleActive,
  onDelete,
}: Props) => {
  const { summary, entries } = detail;
  const own = summary.kind === 'own';
  const [name, setName] = useState(summary.name);
  const [addText, setAddText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ids = entries.map((e) => e.problem.id);

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

  const move = (index: number, by: -1 | 1) => {
    const next = [...ids];
    [next[index], next[index + by]] = [next[index + by], next[index]];
    void run(() => onPatch({ problem_ids: next }));
  };

  // Entries under their section headings, in order; keyed by their first
  // problem, which is unique.
  const sections: { section: string | null; entries: ListEntryOut[] }[] = [];
  for (const entry of entries) {
    const last = sections.at(-1);
    if (last && last.section === entry.section) last.entries.push(entry);
    else sections.push({ section: entry.section, entries: [entry] });
  }

  return (
    <Stack spacing={2}>
      <Stack
        direction="row"
        spacing={1}
        useFlexGap
        sx={{ alignItems: 'center', flexWrap: 'wrap' }}
      >
        <Typography variant="h4" component="h1">
          {summary.name}
        </Typography>
        <Typography color="text.secondary">
          {SOURCE_LABEL[summary.source]} · {summary.kind} · {summary.done} /{' '}
          {summary.total} done
        </Typography>
        <Button
          variant={summary.active ? 'outlined' : 'contained'}
          size="small"
          disabled={busy}
          onClick={() => void run(onToggleActive)}
        >
          {summary.active ? 'Stop using for the plan' : 'Make active'}
        </Button>
      </Stack>
      {summary.active && (
        <Typography variant="body2" color="text.secondary">
          The active {SOURCE_LABEL[summary.source]} list: the daily plan takes
          its next unfinished entries first.
        </Typography>
      )}
      {error && <Alert severity="error">{error}</Alert>}

      {own && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack
            direction="row"
            spacing={1}
            useFlexGap
            sx={{ flexWrap: 'wrap' }}
          >
            <TextField
              size="small"
              label="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <Button
              variant="outlined"
              disabled={busy || name.trim() === '' || name === summary.name}
              onClick={() => void run(() => onPatch({ name: name.trim() }))}
            >
              Rename
            </Button>
            <Button
              color="error"
              disabled={busy}
              onClick={() => {
                if (
                  window.confirm(
                    `Delete ${summary.name}? Problems stay in the library.`,
                  )
                ) {
                  void run(onDelete);
                }
              }}
            >
              Delete list
            </Button>
          </Stack>
        </Paper>
      )}

      <Paper variant="outlined">
        {entries.length === 0 ? (
          <Typography sx={{ p: 2 }} color="text.secondary">
            No entries.
          </Typography>
        ) : (
          sections.map((group) => (
            <List
              key={group.entries[0].problem.id}
              dense
              subheader={
                group.section ? (
                  <ListSubheader>{group.section}</ListSubheader>
                ) : undefined
              }
            >
              {group.entries.map((entry) => {
                const index = ids.indexOf(entry.problem.id);
                return (
                  <ListItem
                    key={entry.problem.id}
                    secondaryAction={
                      own && (
                        <Stack direction="row">
                          <IconButton
                            size="small"
                            aria-label={`Move ${entry.problem.title} up`}
                            disabled={busy || index === 0}
                            onClick={() => move(index, -1)}
                          >
                            <ArrowUpwardIcon fontSize="small" />
                          </IconButton>
                          <IconButton
                            size="small"
                            aria-label={`Move ${entry.problem.title} down`}
                            disabled={busy || index === ids.length - 1}
                            onClick={() => move(index, 1)}
                          >
                            <ArrowDownwardIcon fontSize="small" />
                          </IconButton>
                          <IconButton
                            size="small"
                            aria-label={`Remove ${entry.problem.title}`}
                            disabled={busy}
                            onClick={() =>
                              void run(() =>
                                onPatch({
                                  problem_ids: ids.filter(
                                    (id) => id !== entry.problem.id,
                                  ),
                                }),
                              )
                            }
                          >
                            <DeleteOutlineIcon fontSize="small" />
                          </IconButton>
                        </Stack>
                      )
                    }
                  >
                    <ListItemIcon sx={{ minWidth: 36 }}>
                      {entry.done ? (
                        <CheckCircleIcon color="success" aria-label="Done" />
                      ) : (
                        <RadioButtonUncheckedIcon
                          color="disabled"
                          aria-label="Not done"
                        />
                      )}
                    </ListItemIcon>
                    <ListItemText
                      primary={
                        <Stack
                          direction="row"
                          spacing={1}
                          sx={{ alignItems: 'center' }}
                        >
                          <RouterLink
                            to="/library/$id"
                            params={{ id: entry.problem.id }}
                          >
                            {entry.problem.title}
                          </RouterLink>
                          <RatingChip rating={entry.problem.rating} />
                        </Stack>
                      }
                    />
                  </ListItem>
                );
              })}
            </List>
          ))
        )}
      </Paper>

      {own && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1}>
            <Typography variant="h6" component="h2">
              Add entries
            </Typography>
            <TextField
              multiline
              minRows={3}
              label={`${SOURCE_LABEL[summary.source]} entries, one per line`}
              value={addText}
              onChange={(e) => setAddText(e.target.value)}
            />
            <div>
              <Button
                variant="outlined"
                disabled={busy || addText.trim() === ''}
                onClick={() =>
                  void run(async () => {
                    await onPatch({ add_text: addText });
                    setAddText('');
                  })
                }
              >
                Add to the end
              </Button>
            </div>
            <Unresolved lines={detail.unresolved} />
          </Stack>
        </Paper>
      )}
    </Stack>
  );
};
