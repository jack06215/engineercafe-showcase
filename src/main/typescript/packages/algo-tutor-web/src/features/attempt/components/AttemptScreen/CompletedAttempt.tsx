import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Grid from '@mui/material/Grid';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableRow from '@mui/material/TableRow';
import Typography from '@mui/material/Typography';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { isApiError } from '@/api/client';
import {
  getAttempt,
  patchProblem,
  patchReflection,
  patchSignals,
  requestReport,
} from '@/api/endpoints';
import { keys, patternsQuery } from '@/api/queries';
import type { AttemptOut, Report, Signals } from '@/api/types';
import { formatDay, HELP_LABEL, OUTCOME_LABEL } from '@/common/format';
import { formatMmSs } from '@/common/time';
import { CodeEditor } from '@/components/editor/CodeEditor';
import { PatternPicker } from '@/components/forms/PatternPicker';
import { tutorErrorText } from '@/features/tutor/common/tutorError';

import { isSoftError } from '../../common/attempt';
import { runSoft, type VersionedLane } from '../../common/lane';
import { ReflectionPanel } from '../ReflectionPanel';
import { ReportPanel } from '../ReportPanel';
import { SignalsPanel } from '../SignalsPanel';

type Props = {
  lane: VersionedLane<AttemptOut>;
  record: AttemptOut;
};

const reportKey = (id: string) => [...keys.attempt(id), 'report'] as const;

// SPEC §12.4: polled every 3 s while it's pending or being written.
const usePolledReport = (attempt: AttemptOut) =>
  useQuery({
    queryKey: reportKey(attempt.id),
    queryFn: async (): Promise<Report | null> =>
      (await getAttempt(attempt.id)).report,
    initialData: attempt.report,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'pending' || status === 'generating' ? 3000 : false;
    },
  });

const SavedPanel = ({ attempt }: { attempt: AttemptOut }) => (
  <Stack spacing={1} component="section" aria-label="Saved">
    <Typography variant="h6" component="h2">
      Attempt saved
    </Typography>
    <Table size="small">
      <TableBody>
        <TableRow>
          <TableCell component="th">Outcome</TableCell>
          <TableCell>
            {attempt.outcome ? OUTCOME_LABEL[attempt.outcome] : '–'}
          </TableCell>
        </TableRow>
        <TableRow>
          <TableCell component="th">Time</TableCell>
          <TableCell>{formatMmSs(attempt.active_seconds)}</TableCell>
        </TableRow>
        <TableRow>
          <TableCell component="th">Help</TableCell>
          <TableCell>{HELP_LABEL[attempt.help]}</TableCell>
        </TableRow>
        <TableRow>
          <TableCell component="th">Next review</TableCell>
          <TableCell>
            {attempt.next_review_date
              ? formatDay(attempt.next_review_date)
              : 'Not scheduled'}
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>
  </Stack>
);

// A finished attempt (SPEC §6.7): what was saved, Algo-chan's report, the
// reflection, signals, pattern labels and the saved code. During another
// hidden assessment the reflection, signals and report are null and stay
// hidden.
export const CompletedAttempt = ({ lane, record }: Props) => {
  const queryClient = useQueryClient();
  const report = usePolledReport(record);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [signals, setSignals] = useState<Signals | null>(record.signals);
  const [patterns, setPatterns] = useState<string[] | null>(record.patterns);
  const patternOptions = useQuery({
    ...patternsQuery,
    enabled: record.patterns !== null,
  });

  const askForReport = async () => {
    setRequesting(true);
    setRequestError(null);
    try {
      const pending = await requestReport(record.id);
      queryClient.setQueryData(reportKey(record.id), pending);
    } catch (e) {
      setRequestError(tutorErrorText(e));
    } finally {
      setRequesting(false);
    }
  };

  const changeSignals = async (patch: Partial<Signals>) => {
    if (!signals) return;
    const before = signals;
    setSignals({ ...signals, ...patch });
    try {
      setSignals((await patchSignals(record.id, patch)).signals);
    } catch {
      setSignals(before);
    }
  };

  const changePatterns = async (ids: string[]) => {
    const before = patterns;
    setPatterns(ids);
    try {
      const detail = await patchProblem(record.problem.id, { patterns: ids });
      setPatterns(detail.patterns);
    } catch {
      setPatterns(before);
    }
  };

  return (
    <Grid container spacing={3}>
      <Grid size={{ xs: 12, lg: 7 }}>
        <Stack spacing={2}>
          {lane.error !== null && (
            <Alert
              severity="warning"
              action={
                <Button
                  color="inherit"
                  size="small"
                  onClick={() =>
                    void getAttempt(record.id).then((a) => lane.replace(a))
                  }
                >
                  Reload
                </Button>
              }
            >
              {isApiError(lane.error, 'STALE')
                ? 'This attempt changed elsewhere. Reload it, then save again.'
                : String(lane.error)}
            </Alert>
          )}
          <Paper variant="outlined" sx={{ p: 2 }}>
            <SavedPanel attempt={record} />
          </Paper>
          {report.data && (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <ReportPanel
                report={report.data}
                onRequest={() => void askForReport()}
                requesting={requesting}
                requestError={requestError}
              />
            </Paper>
          )}
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Stack spacing={1}>
              <Typography variant="h6" component="h2">
                Saved code
              </Typography>
              {record.solution_path && (
                <Typography variant="body2">
                  From <code>{record.solution_path}</code>
                </Typography>
              )}
              <CodeEditor
                label="Saved code"
                language={record.language}
                value={record.code}
                readOnly
              />
              {record.notes && (
                <Typography
                  variant="body2"
                  sx={{ whiteSpace: 'pre-wrap', mt: 1 }}
                >
                  {record.notes}
                </Typography>
              )}
            </Stack>
          </Paper>
        </Stack>
      </Grid>
      <Grid size={{ xs: 12, lg: 5 }}>
        <Stack spacing={2}>
          {record.mistake_labels !== null && record.takeaway !== null && (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <ReflectionPanel
                labels={record.mistake_labels}
                takeaway={record.takeaway}
                onSave={async (labels, takeaway) => {
                  await runSoft(
                    lane,
                    (r) =>
                      patchReflection(r.id, {
                        version: r.version,
                        mistake_labels: labels,
                        takeaway,
                      }),
                    isSoftError,
                  );
                  void queryClient.invalidateQueries({
                    queryKey: keys.mistakes,
                  });
                }}
              />
            </Paper>
          )}
          {signals && (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <SignalsPanel
                signals={signals}
                onChange={(patch) => void changeSignals(patch)}
              />
            </Paper>
          )}
          {patterns !== null && (
            <Paper variant="outlined" sx={{ p: 2 }}>
              <PatternPicker
                value={patterns}
                options={patternOptions.data ?? []}
                onChange={(ids) => void changePatterns(ids)}
              />
            </Paper>
          )}
        </Stack>
      </Grid>
    </Grid>
  );
};
