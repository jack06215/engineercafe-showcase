import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { createLink } from '@tanstack/react-router';
import { useState } from 'react';

import type { MistakeEntry, MistakeLabel } from '@/api/types';
import { formatTimestamp, MISTAKE_LABEL } from '@/common/format';

const RouterLink = createLink(Link);

type Props = {
  items: MistakeEntry[];
};

const matches = (entry: MistakeEntry, query: string) => {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [
    entry.problem.title,
    entry.takeaway,
    ...entry.mistake_labels.map((l) => MISTAKE_LABEL[l]),
  ].some((text) => text.toLowerCase().includes(q));
};

// The mistake notebook (SPEC §11.3): finished attempts with a mistake
// label or a takeaway, newest first.
export const MistakesView = ({ items }: Props) => {
  const [query, setQuery] = useState('');
  const [label, setLabel] = useState<MistakeLabel | ''>('');
  const shown = items.filter(
    (e) =>
      matches(e, query) && (label === '' || e.mistake_labels.includes(label)),
  );

  return (
    <Stack spacing={2}>
      <Typography variant="h4" component="h1">
        Mistakes
      </Typography>
      {items.length === 0 ? (
        <Typography color="text.secondary">
          No lessons yet — add a mistake label or takeaway after saving an
          attempt
        </Typography>
      ) : (
        <>
          <Stack
            direction="row"
            spacing={1.5}
            useFlexGap
            sx={{ flexWrap: 'wrap' }}
          >
            <TextField
              size="small"
              label="Search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              sx={{ minWidth: 240 }}
            />
            <TextField
              select
              size="small"
              label="Mistake type"
              value={label}
              onChange={(e) => setLabel(e.target.value as MistakeLabel | '')}
              sx={{ minWidth: 200 }}
            >
              <MenuItem value="">Any</MenuItem>
              {(Object.keys(MISTAKE_LABEL) as MistakeLabel[]).map((l) => (
                <MenuItem key={l} value={l}>
                  {MISTAKE_LABEL[l]}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          <Paper variant="outlined">
            <List disablePadding>
              {shown.map((entry) => (
                <ListItem
                  key={entry.attempt_id}
                  divider
                  alignItems="flex-start"
                >
                  <ListItemText
                    primary={
                      <Stack
                        direction="row"
                        spacing={1}
                        useFlexGap
                        sx={{ alignItems: 'center', flexWrap: 'wrap' }}
                      >
                        <RouterLink
                          to="/attempts/$id"
                          params={{ id: entry.attempt_id }}
                        >
                          {entry.problem.title}
                        </RouterLink>
                        {entry.mistake_labels.map((l) => (
                          <Chip key={l} size="small" label={MISTAKE_LABEL[l]} />
                        ))}
                      </Stack>
                    }
                    secondary={
                      <>
                        {entry.takeaway && (
                          <Typography
                            component="span"
                            sx={{ display: 'block' }}
                          >
                            {entry.takeaway}
                          </Typography>
                        )}
                        {formatTimestamp(entry.finished_at)}
                      </>
                    }
                  />
                </ListItem>
              ))}
              {shown.length === 0 && (
                <ListItem>
                  <ListItemText secondary="Nothing matches." />
                </ListItem>
              )}
            </List>
          </Paper>
        </>
      )}
    </Stack>
  );
};
