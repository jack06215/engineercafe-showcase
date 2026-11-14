import Grid from '@mui/material/Grid';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import type { Notebook, NotebookPatch, TopicDetail } from '@/api/types';

import { NotebookEditor } from '../NotebookEditor';
import { ProblemsAttempted } from '../ProblemsAttempted';
import { describeChange, LevelBadge, LevelBar } from '../TopicsView';

type Props = {
  detail: TopicDetail;
  onSave: (patch: NotebookPatch) => Promise<Notebook>;
  loadSaved: () => Promise<Notebook>;
};

// A topic page (SPEC §11.1): the level, your notebook and the problems
// you've attempted in it.
export const TopicView = ({ detail, onSave, loadSaved }: Props) => {
  const { level } = detail;
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        <Typography variant="h4" component="h1">
          {level.name}
        </Typography>
        <LevelBadge topic={level} />
      </Stack>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1} component="section" aria-label="Level">
          <Typography>
            Level <strong>{level.level}</strong> · target {detail.target_rating}
          </Typography>
          <LevelBar level={level.level} target={detail.target_rating} />
          <Typography variant="body2" color="text.secondary">
            {level.last_change
              ? describeChange(level.last_change)
              : 'Not practised yet'}
          </Typography>
        </Stack>
      </Paper>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 7 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <NotebookEditor
              notebook={detail.notebook}
              storageKey={`topic:${level.id}`}
              onSave={onSave}
              loadSaved={loadSaved}
            />
          </Paper>
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <ProblemsAttempted
              problems={detail.problems}
              unseenCount={detail.unseen_count}
            />
          </Paper>
        </Grid>
      </Grid>
    </Stack>
  );
};
