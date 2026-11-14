import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Grid from '@mui/material/Grid';
import Link from '@mui/material/Link';
import MenuItem from '@mui/material/MenuItem';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { createLink } from '@tanstack/react-router';
import { useState } from 'react';

import type {
  PatternSummary,
  ProblemDetail,
  ProblemPatch,
  ReviewPatch,
} from '@/api/types';
import {
  formatDay,
  HELP_LABEL,
  OUTCOME_LABEL,
  SOURCE_LABEL,
} from '@/common/format';
import { formatMmSs } from '@/common/time';
import { PatternPicker } from '@/components/forms/PatternPicker';
import { RatingChip } from '@/components/ui/RatingChip';

import { ReviewEditor } from './ReviewEditor';

const RouterLink = createLink(Link);

// The "None" choice of the topic override.
const NO_TOPIC = '__none__';

type Props = {
  detail: ProblemDetail;
  topics: { id: string; name: string }[];
  patterns: PatternSummary[];
  onPatch: (patch: ProblemPatch) => Promise<void>;
  onReview: (patch: ReviewPatch) => Promise<void>;
  onStart: () => Promise<void>;
};

const Section = ({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) => (
  <Paper variant="outlined" sx={{ p: 2 }}>
    <Stack spacing={1.5} component="section" aria-label={title}>
      <Typography variant="h6" component="h2">
        {title}
      </Typography>
      {children}
    </Stack>
  </Paper>
);

// A problem (SPEC §14 Problem): its facts, primary topic with override,
// patterns, notes, Start attempt, the review schedule and every attempt.
export const ProblemView = ({
  detail,
  topics,
  patterns,
  onPatch,
  onReview,
  onStart,
}: Props) => {
  const { problem } = detail;
  const [topic, setTopic] = useState(detail.topic_id ?? NO_TOPIC);
  const [notes, setNotes] = useState(detail.notes);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const topicName = (id: string | null) =>
    id === null ? 'None' : (topics.find((t) => t.id === id)?.name ?? id);

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
    <Stack spacing={2}>
      <Stack
        direction="row"
        spacing={1}
        useFlexGap
        sx={{ alignItems: 'center', flexWrap: 'wrap' }}
      >
        <Typography variant="h4" component="h1">
          {problem.number !== null && `${problem.number}. `}
          {problem.title}
        </Typography>
        <RatingChip rating={problem.rating} />
        <Button
          variant="contained"
          onClick={() => void run(onStart)}
          disabled={busy}
        >
          Start attempt
        </Button>
        <Button
          href={problem.url}
          target="_blank"
          rel="noreferrer"
          endIcon={<OpenInNewIcon />}
        >
          Open on {SOURCE_LABEL[problem.source]}
        </Button>
      </Stack>
      {error && <Alert severity="error">{error}</Alert>}

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Section title="Facts">
            <Table size="small">
              <TableBody>
                <TableRow>
                  <TableCell component="th">Source</TableCell>
                  <TableCell>
                    {SOURCE_LABEL[problem.source]}
                    {problem.contest && ` · ${problem.contest}`} ·{' '}
                    {detail.external_id}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell component="th">Difficulty</TableCell>
                  <TableCell>
                    {problem.difficulty ?? '–'}
                    {detail.paid_only && ' · paid only'}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell component="th">Rating</TableCell>
                  <TableCell>
                    {problem.rating
                      ? `${problem.rating.estimated ? '≈' : ''}${problem.rating.value}${problem.rating.estimated ? ' (estimate)' : ''}`
                      : 'Unrated: never planned or levelled'}
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell component="th">NeetCode category</TableCell>
                  <TableCell>{detail.neetcode_category ?? '–'}</TableCell>
                </TableRow>
                <TableRow>
                  <TableCell component="th">Tags</TableCell>
                  <TableCell>
                    <Stack
                      direction="row"
                      spacing={0.5}
                      useFlexGap
                      sx={{ flexWrap: 'wrap' }}
                    >
                      {detail.source_tags.length === 0
                        ? '–'
                        : detail.source_tags.map((t) => (
                            <Chip key={t} size="small" label={t} />
                          ))}
                    </Stack>
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell component="th">Lists</TableCell>
                  <TableCell>
                    {detail.lists.length === 0
                      ? '–'
                      : detail.lists.map((l, i) => (
                          <span key={l.id}>
                            {i > 0 && ', '}
                            <RouterLink to="/lists/$id" params={{ id: l.id }}>
                              {l.name}
                            </RouterLink>
                          </span>
                        ))}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </Section>
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}>
          <Stack spacing={2}>
            {problem.source === 'leetcode' && (
              <Section title="Primary topic">
                <Typography variant="body2" color="text.secondary">
                  {detail.topic_overridden
                    ? `Your override: ${topicName(detail.topic_id)}.`
                    : `Assigned automatically: ${topicName(detail.topic_id)}.`}{' '}
                  Changing it moves this problem's past attempts to the new
                  topic's level.
                </Typography>
                <Stack
                  direction="row"
                  spacing={1}
                  useFlexGap
                  sx={{ flexWrap: 'wrap' }}
                >
                  <TextField
                    select
                    size="small"
                    label="Topic"
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                    sx={{ minWidth: 220 }}
                  >
                    <MenuItem value={NO_TOPIC}>None</MenuItem>
                    {topics.map((t) => (
                      <MenuItem key={t.id} value={t.id}>
                        {t.name}
                      </MenuItem>
                    ))}
                  </TextField>
                  <Button
                    variant="outlined"
                    disabled={busy}
                    onClick={() =>
                      void run(() =>
                        onPatch({
                          topic_id: topic === NO_TOPIC ? null : topic,
                        }),
                      )
                    }
                  >
                    Override
                  </Button>
                  {detail.topic_overridden && (
                    <Button
                      disabled={busy}
                      onClick={() =>
                        void run(() => onPatch({ reset_topic: true }))
                      }
                    >
                      Reset
                    </Button>
                  )}
                </Stack>
              </Section>
            )}
            <Paper variant="outlined" sx={{ p: 2 }}>
              <PatternPicker
                value={detail.patterns}
                options={patterns}
                onChange={(ids) => void run(() => onPatch({ patterns: ids }))}
                disabled={busy}
              />
            </Paper>
            <Section title="Review schedule">
              {detail.review ? (
                <ReviewEditor
                  key={`${detail.review.version}`}
                  review={detail.review}
                  attempted={detail.attempts.length > 0}
                  onSave={onReview}
                />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Scheduled once you finish an attempt.
                </Typography>
              )}
            </Section>
          </Stack>
        </Grid>
      </Grid>

      <Section title="Your notes">
        <TextField
          multiline
          minRows={3}
          label="Notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
        <div>
          <Button
            variant="outlined"
            disabled={busy || notes === detail.notes}
            onClick={() => void run(() => onPatch({ notes }))}
          >
            Save notes
          </Button>
        </div>
      </Section>

      <Section title="Attempts">
        {detail.attempts.length === 0 ? (
          <Typography color="text.secondary">No attempts yet.</Typography>
        ) : (
          <Table size="small" aria-label="Attempts">
            <TableHead>
              <TableRow>
                <TableCell>Date</TableCell>
                <TableCell>Outcome</TableCell>
                <TableCell>Help</TableCell>
                <TableCell>Time</TableCell>
                <TableCell>Confidence</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {detail.attempts.map((a) => (
                <TableRow key={a.id} hover>
                  <TableCell>
                    <RouterLink to="/attempts/$id" params={{ id: a.id }}>
                      {formatDay(a.study_date)}
                    </RouterLink>
                  </TableCell>
                  <TableCell>
                    {a.outcome
                      ? OUTCOME_LABEL[a.outcome]
                      : a.status === 'completed'
                        ? '–'
                        : 'In progress'}
                  </TableCell>
                  <TableCell>{HELP_LABEL[a.help]}</TableCell>
                  <TableCell>{formatMmSs(a.active_seconds)}</TableCell>
                  <TableCell>{a.confidence ?? '–'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Section>
    </Stack>
  );
};
