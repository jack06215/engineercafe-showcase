import Link from '@mui/material/Link';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { createLink } from '@tanstack/react-router';

import type { NotebookProblem } from '@/api/types';
import { OUTCOME_LABEL } from '@/common/format';
import { RatingChip } from '@/components/ui/RatingChip';

const RouterLink = createLink(Link);

type Props = {
  problems: NotebookProblem[];
  // Topic pages count the unseen problems without naming them (SPEC
  // §11.1), so browsing can't expose them.
  unseenCount?: number;
};

export const ProblemsAttempted = ({ problems, unseenCount }: Props) => (
  <Stack spacing={1} component="section" aria-label="Problems">
    <Typography variant="h6" component="h2">
      Problems you've attempted
    </Typography>
    {problems.length === 0 ? (
      <Typography color="text.secondary">None yet.</Typography>
    ) : (
      <List dense disablePadding>
        {problems.map(({ problem, attempts, latest_outcome }) => (
          <ListItem key={problem.id} disableGutters>
            <ListItemText
              primary={
                <Stack
                  direction="row"
                  spacing={1}
                  sx={{ alignItems: 'center' }}
                >
                  <RouterLink to="/library/$id" params={{ id: problem.id }}>
                    {problem.title}
                  </RouterLink>
                  <RatingChip rating={problem.rating} />
                </Stack>
              }
              secondary={`${attempts} ${attempts === 1 ? 'attempt' : 'attempts'}${
                latest_outcome
                  ? ` · latest: ${OUTCOME_LABEL[latest_outcome]}`
                  : ''
              }`}
            />
          </ListItem>
        ))}
      </List>
    )}
    {unseenCount !== undefined && (
      <Typography variant="body2" color="text.secondary">
        {unseenCount} unseen {unseenCount === 1 ? 'problem' : 'problems'} in
        this topic, kept hidden so they stay fair transfer checks.
      </Typography>
    )}
  </Stack>
);
