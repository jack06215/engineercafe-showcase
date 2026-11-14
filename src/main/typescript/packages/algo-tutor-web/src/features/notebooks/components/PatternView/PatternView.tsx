import Alert from '@mui/material/Alert';
import Grid from '@mui/material/Grid';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import type { Notebook, NotebookPatch, PatternDetail } from '@/api/types';
import { Markdown } from '@/components/ui/Markdown';

import { repoPathFor } from '../../common/repoPath';
import { NotebookEditor } from '../NotebookEditor';
import { ProblemsAttempted } from '../ProblemsAttempted';

type Props = {
  detail: PatternDetail;
  onSave: (patch: NotebookPatch) => Promise<Notebook>;
  loadSaved: () => Promise<Notebook>;
};

// A pattern page (SPEC §11.2): the common_coding_pattern README, read live
// and read-only, beside your own notebook.
export const PatternView = ({ detail, onSave, loadSaved }: Props) => (
  <Stack spacing={2}>
    <Typography variant="h4" component="h1">
      {detail.pattern.name}
    </Typography>
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, md: 7 }}>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1} component="section" aria-label="README">
            <Typography variant="caption" color="text.secondary">
              {detail.readme_path}
            </Typography>
            {detail.readme_markdown === null ? (
              <Alert severity="warning">
                README not found at <code>{detail.readme_path}</code>
              </Alert>
            ) : (
              <Markdown
                linkHref={(href) => repoPathFor(detail.readme_path, href)}
              >
                {detail.readme_markdown}
              </Markdown>
            )}
          </Stack>
        </Paper>
      </Grid>
      <Grid size={{ xs: 12, md: 5 }}>
        <Stack spacing={2}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <NotebookEditor
              notebook={detail.notebook}
              storageKey={`pattern:${detail.pattern.id}`}
              onSave={onSave}
              loadSaved={loadSaved}
            />
          </Paper>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <ProblemsAttempted problems={detail.problems} />
          </Paper>
        </Stack>
      </Grid>
    </Grid>
  </Stack>
);
