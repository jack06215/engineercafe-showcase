import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import FormControlLabel from '@mui/material/FormControlLabel';
import Link from '@mui/material/Link';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { createLink } from '@tanstack/react-router';
import { useState } from 'react';

import type {
  BackupStatus,
  BankStatus,
  ListSummary,
  SettingsOut,
  SettingsPatch,
  TutorStatus,
  TutorTest,
} from '@/api/types';
import { formatTimestamp, TUTOR_ERROR_MESSAGE } from '@/common/format';

const RouterLink = createLink(Link);

type Props = {
  settings: SettingsOut;
  bank: BankStatus;
  lists: ListSummary[];
  backup: BackupStatus | undefined;
  tutor: TutorStatus | undefined;
  onSave: (patch: SettingsPatch) => Promise<void>;
  onRefreshBank: () => Promise<void>;
  onBackup: () => Promise<void>;
  onTestTutor: () => Promise<TutorTest>;
  // Null when there's no plan today (or an assessment hides it).
  onReplan: (() => Promise<void>) | null;
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

const useAction = () => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const run = async (fn: () => Promise<unknown>, doneText?: string) => {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      await fn();
      if (doneText) setDone(doneText);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, done, run };
};

const Feedback = ({
  error,
  done,
}: {
  error: string | null;
  done: string | null;
}) => (
  <>
    {error && <Alert severity="error">{error}</Alert>}
    {done && <Alert severity="success">{done}</Alert>}
  </>
);

// Settings (SPEC §13, §14): the plan's numbers, active lists, the problem
// bank, backups and the tutor.
export const SettingsView = ({
  settings,
  bank,
  lists,
  backup,
  tutor,
  onSave,
  onRefreshBank,
  onBackup,
  onTestTutor,
  onReplan,
}: Props) => {
  const [perDay, setPerDay] = useState(String(settings.questions_per_day));
  const [atcoder, setAtcoder] = useState(String(settings.atcoder_per_day));
  const [target, setTarget] = useState(String(settings.target_rating));
  const [paid, setPaid] = useState(settings.include_paid_only);
  const [test, setTest] = useState<TutorTest | null>(null);
  const plan = useAction();
  const bankAction = useAction();
  const backupAction = useAction();
  const tutorAction = useAction();
  const replan = useAction();

  const n = (text: string) => Number(text);
  const perDayOk =
    Number.isInteger(n(perDay)) && n(perDay) >= 1 && n(perDay) <= 20;
  const atcoderOk =
    Number.isInteger(n(atcoder)) && n(atcoder) >= 0 && n(atcoder) <= 10;
  const targetOk =
    Number.isInteger(n(target)) &&
    n(target) >= 1200 &&
    n(target) <= 2600 &&
    n(target) % 50 === 0;
  // PATCH /settings leaves null fields alone, so send only what changed.
  const patch: SettingsPatch = {
    ...(n(perDay) !== settings.questions_per_day && {
      questions_per_day: n(perDay),
    }),
    ...(n(atcoder) !== settings.atcoder_per_day && {
      atcoder_per_day: n(atcoder),
    }),
    ...(n(target) !== settings.target_rating && { target_rating: n(target) }),
    ...(paid !== settings.include_paid_only && { include_paid_only: paid }),
  };
  const changed = Object.keys(patch).length > 0;
  const listName = (id: string | null) =>
    id === null ? null : (lists.find((l) => l.id === id) ?? null);
  const activeLists = [
    ['LeetCode', listName(settings.active_list_leetcode)],
    ['AtCoder', listName(settings.active_list_atcoder)],
  ] as const;

  return (
    <Stack spacing={2}>
      <Typography variant="h4" component="h1">
        Settings
      </Typography>

      <Section title="Daily plan">
        <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: 'wrap' }}>
          <TextField
            size="small"
            type="number"
            label="Questions per day"
            value={perDay}
            onChange={(e) => setPerDay(e.target.value)}
            error={!perDayOk}
            helperText="LeetCode lane, 1–20"
            slotProps={{ htmlInput: { min: 1, max: 20 } }}
          />
          <TextField
            size="small"
            type="number"
            label="AtCoder problems per day"
            value={atcoder}
            onChange={(e) => setAtcoder(e.target.value)}
            error={!atcoderOk}
            helperText="From the active AtCoder list, 0–10"
            slotProps={{ htmlInput: { min: 0, max: 10 } }}
          />
          <TextField
            size="small"
            type="number"
            label="Target rating"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            error={!targetOk}
            helperText="1200–2600, in steps of 50"
            slotProps={{ htmlInput: { min: 1200, max: 2600, step: 50 } }}
          />
        </Stack>
        <FormControlLabel
          control={
            <Switch
              checked={paid}
              onChange={(e) => setPaid(e.target.checked)}
            />
          }
          label="Include paid-only problems"
        />
        <Stack direction="row" spacing={1}>
          <Button
            variant="contained"
            disabled={
              plan.busy || !changed || !perDayOk || !atcoderOk || !targetOk
            }
            onClick={() => void plan.run(() => onSave(patch), 'Saved.')}
          >
            Save
          </Button>
          {onReplan && (
            <Button
              variant="outlined"
              disabled={replan.busy}
              onClick={() =>
                void replan.run(
                  onReplan,
                  "Re-planned today's unstarted questions.",
                )
              }
            >
              Re-plan today
            </Button>
          )}
        </Stack>
        <Feedback
          error={plan.error ?? replan.error}
          done={plan.done ?? replan.done}
        />
        <Typography variant="body2" color="text.secondary">
          Timezone: {settings.timezone} (this computer's, read at every start)
        </Typography>
      </Section>

      <Section title="Active lists">
        {activeLists.map(([source, list]) => (
          <Typography key={source} variant="body2">
            {source}:{' '}
            {list ? (
              <RouterLink to="/lists/$id" params={{ id: list.id }}>
                {list.name}
              </RouterLink>
            ) : (
              'none'
            )}
          </Typography>
        ))}
        <div>
          <RouterLink to="/lists">Choose in Lists</RouterLink>
        </div>
      </Section>

      <Section title="LeetCode problem bank">
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          {bank.status === 'running' && (
            <CircularProgress size={18} aria-label="Downloading" />
          )}
          <Typography variant="body2">
            {bank.status === 'never'
              ? 'Not downloaded yet.'
              : bank.status === 'running'
                ? 'Downloading…'
                : bank.status === 'failed'
                  ? 'The last download failed.'
                  : `${bank.problems.toLocaleString('en')} problems, ${bank.estimated.toLocaleString('en')} with estimated ratings${bank.method ? ` (${bank.method})` : ''}.`}
            {bank.fetched_at &&
              ` Last fetched ${formatTimestamp(bank.fetched_at)}.`}
          </Typography>
        </Stack>
        {bank.error && <Alert severity="error">{bank.error}</Alert>}
        {bank.unknown_tags.length > 0 && (
          <Stack
            direction="row"
            spacing={0.5}
            useFlexGap
            sx={{ flexWrap: 'wrap', alignItems: 'center' }}
          >
            <Typography variant="body2">Tags with no topic mapping:</Typography>
            {bank.unknown_tags.map((t) => (
              <Chip key={t} size="small" label={t} />
            ))}
          </Stack>
        )}
        <div>
          <Button
            variant="outlined"
            disabled={bankAction.busy || bank.status === 'running'}
            onClick={() => void bankAction.run(onRefreshBank)}
          >
            {bank.status === 'never' ? 'Download' : 'Refresh'}
          </Button>
        </div>
        <Feedback error={bankAction.error} done={null} />
      </Section>

      <Section title="Backups">
        <Typography variant="body2">
          {backup?.last_backup_at
            ? `Last backup ${formatTimestamp(backup.last_backup_at)}`
            : settings.last_backup_at
              ? `Last backup ${formatTimestamp(settings.last_backup_at)}`
              : 'No backup yet.'}
          {backup?.path && ` · ${backup.path}`}
          {backup && ` · the newest ${backup.kept} are kept`}
        </Typography>
        <div>
          <Button
            variant="outlined"
            disabled={backupAction.busy}
            onClick={() => void backupAction.run(onBackup, 'Backed up.')}
          >
            Back up now
          </Button>
        </div>
        <Feedback error={backupAction.error} done={backupAction.done} />
      </Section>

      <Section title="Algo-chan">
        {tutor ? (
          <>
            <Typography variant="body2">
              {tutor.enabled ? 'On' : 'Off'} · {tutor.provider} · {tutor.model}
              {tutor.pending_reports > 0 &&
                ` · ${tutor.pending_reports} reports waiting`}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {tutor.leaves_machine
                ? `Your code, notes and problem details are sent to ${tutor.provider}.`
                : 'The model runs on this machine; nothing leaves it.'}{' '}
              Provider and model are set in config.yaml.
            </Typography>
          </>
        ) : (
          <Typography variant="body2" color="text.secondary">
            Loading…
          </Typography>
        )}
        <div>
          <Button
            variant="outlined"
            disabled={tutorAction.busy}
            onClick={() =>
              void tutorAction.run(async () => setTest(await onTestTutor()))
            }
          >
            Test connection
          </Button>
        </div>
        {test &&
          (test.ok ? (
            <Alert severity="success">
              {test.provider} · {test.model}
              {test.latency_ms !== null && ` · ${test.latency_ms} ms`}
            </Alert>
          ) : (
            <Alert severity="error">
              {test.error_kind
                ? TUTOR_ERROR_MESSAGE[test.error_kind]
                : 'Failed.'}
              {test.message && ` ${test.message}`}
            </Alert>
          ))}
        <Feedback error={tutorAction.error} done={null} />
      </Section>
    </Stack>
  );
};
