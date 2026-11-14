import Chip from '@mui/material/Chip';
import List from '@mui/material/List';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { createLink } from '@tanstack/react-router';

import type { PatternSummary } from '@/api/types';

const LinkRow = createLink(ListItemButton);

type Props = {
  patterns: PatternSummary[];
};

// Patterns (SPEC §5.8, §14): common_coding_pattern's 16, in folder order.
export const PatternsView = ({ patterns }: Props) => (
  <Stack spacing={2}>
    <Typography variant="h4" component="h1">
      Patterns
    </Typography>
    <Paper variant="outlined">
      <List disablePadding>
        {[...patterns]
          .sort((a, b) => a.position - b.position)
          .map((p) => (
            <LinkRow
              key={p.id}
              to="/patterns/$id"
              params={{ id: p.id }}
              divider
            >
              <ListItemText
                primary={
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{ alignItems: 'center' }}
                  >
                    <span>
                      {String(p.position).padStart(2, '0')}. {p.name}
                    </span>
                    {p.missing && (
                      <Chip
                        size="small"
                        color="warning"
                        label="README missing"
                      />
                    )}
                  </Stack>
                }
                secondary={`${p.problems} ${p.problems === 1 ? 'problem' : 'problems'} labelled`}
              />
            </LinkRow>
          ))}
      </List>
    </Paper>
  </Stack>
);
