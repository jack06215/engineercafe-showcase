import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import type { Report } from '@/api/types';
import { Markdown } from '@/components/ui/Markdown';
import { tutorKindText } from '@/features/tutor/common/tutorError';

type Props = {
  report: Report;
  onRequest: () => void;
  requesting?: boolean;
  // A failed request (e.g. the tutor is off), shown under the panel.
  requestError?: string | null;
};

const SECTIONS = [
  ['summary', 'Summary'],
  ['strengths', 'What went well'],
  ['improvements', 'What to improve'],
  ['complexity', 'Complexity'],
  ['practice', 'Practise next'],
] as const;

// Algo-chan's report on a finished attempt (SPEC §12.4).
export const ReportPanel = ({
  report,
  onRequest,
  requesting = false,
  requestError = null,
}: Props) => {
  return (
    <Stack spacing={1.5} component="section" aria-label="Report">
      <Typography variant="h6" component="h2">
        Algo-chan's report
      </Typography>
      {report.status === 'none' && (
        <div>
          <Button variant="outlined" onClick={onRequest} disabled={requesting}>
            Ask for a report
          </Button>
        </div>
      )}
      {report.status === 'pending' && (
        <Typography color="text.secondary" role="status">
          Waiting for Algo-chan…
        </Typography>
      )}
      {report.status === 'generating' && (
        <Typography color="text.secondary" role="status">
          Algo-chan is writing a report…
        </Typography>
      )}
      {report.status === 'failed' && (
        <Alert
          severity="warning"
          action={
            <Button
              color="inherit"
              size="small"
              onClick={onRequest}
              disabled={requesting}
            >
              Try again
            </Button>
          }
        >
          {tutorKindText(report.error_kind, report.error_message)}
        </Alert>
      )}
      {report.status === 'done' &&
        SECTIONS.map(([field, title]) =>
          report[field] ? (
            <div key={field}>
              <Typography variant="subtitle2">{title}</Typography>
              <Markdown>{report[field] ?? ''}</Markdown>
            </div>
          ) : null,
        )}
      {report.status === 'done' && report.model && (
        <Typography variant="caption" color="text.secondary">
          Written by {report.model}
        </Typography>
      )}
      {requestError && <Alert severity="error">{requestError}</Alert>}
    </Stack>
  );
};
