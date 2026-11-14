import LockOutlinedIcon from '@mui/icons-material/LockOutlined';
import Accordion from '@mui/material/Accordion';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { createLink } from '@tanstack/react-router';

import type { Desk, Lane, PlanItemOut } from '@/api/types';
import { formatDay, greeting } from '@/common/format';

import { type PlanItemActions, PlanItemRow } from '../PlanItemRow';

const ButtonLink = createLink(Button);

export type DeskActions = PlanItemActions & {
  resumeAttempt: (attemptId: string) => void;
  replan: () => void;
};

type Props = {
  desk: Desk;
  actions: DeskActions;
  // For the greeting.
  now: Date;
  busyItemId?: string | null;
  replanning?: boolean;
};

const LANE_TITLE: Record<Lane, string> = {
  leetcode: 'LeetCode',
  atcoder: 'AtCoder',
};

const DISPOSITION_LABEL = {
  swap: 'Replaced',
  snooze: 'Postponed',
  skip: 'Skipped today',
} as const;

// SPEC §9: during a hidden assessment the desk shows nothing but this.
const AssessmentInProgress = ({
  attemptId,
  onResume,
}: {
  attemptId: string | null;
  onResume: (attemptId: string) => void;
}) => (
  <Card variant="outlined">
    <CardContent>
      <Stack spacing={2} sx={{ alignItems: 'flex-start' }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <LockOutlinedIcon color="primary" />
          <Typography variant="h5" component="h1">
            Assessment in progress
          </Typography>
        </Stack>
        <Typography color="text.secondary">
          Spot the approach yourself. Your notebooks and levels open again once
          you finish.
        </Typography>
        {attemptId && (
          <Button variant="contained" onClick={() => onResume(attemptId)}>
            Resume
          </Button>
        )}
      </Stack>
    </CardContent>
  </Card>
);

const LaneSection = ({
  lane,
  items,
  desk,
  actions,
  busyItemId,
}: {
  lane: Lane;
  items: PlanItemOut[];
  desk: Desk;
  actions: DeskActions;
  busyItemId: string | null;
}) => {
  const shown = items.filter((i) => i.status !== 'skipped');
  const movable = shown.filter((i) => i.status !== 'completed');
  return (
    <section aria-label={`${LANE_TITLE[lane]} lane`}>
      <Typography variant="h6" component="h2" gutterBottom>
        {LANE_TITLE[lane]}
      </Typography>
      {shown.length === 0 ? (
        <Typography color="text.secondary">
          {lane === 'atcoder'
            ? 'Nothing from AtCoder today.'
            : 'Nothing planned in this lane.'}
        </Typography>
      ) : (
        <List disablePadding>
          {shown.map((item) => {
            const index = movable.indexOf(item);
            return (
              <PlanItemRow
                key={item.id}
                item={item}
                actions={actions}
                today={desk.today}
                canStart={desk.active_attempt === null}
                canMoveUp={index > 0}
                canMoveDown={index >= 0 && index < movable.length - 1}
                busy={busyItemId === item.id}
              />
            );
          })}
        </List>
      )}
    </section>
  );
};

// The study desk (SPEC §14 Desk): today's plan in the LeetCode and AtCoder
// lanes, with each item's actions.
export const DeskView = ({
  desk,
  actions,
  now,
  busyItemId = null,
  replanning = false,
}: Props) => {
  if (desk.hidden_assessment) {
    return (
      <AssessmentInProgress
        attemptId={desk.active_attempt?.id ?? null}
        onResume={actions.resumeAttempt}
      />
    );
  }

  const items = desk.plan?.items ?? [];
  const byLane = (lane: Lane) =>
    items
      .filter((i) => i.lane === lane)
      .sort((a, b) => a.position - b.position);
  const skipped = items.filter((i) => i.status === 'skipped');
  const active = desk.active_attempt;
  const activeInPlan = items.some((i) => i.attempt_id === active?.id);

  return (
    <Stack spacing={3}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        sx={{ justifyContent: 'space-between', alignItems: { sm: 'flex-end' } }}
      >
        <div>
          <Typography variant="h4" component="h1">
            {greeting(now.getHours())}
          </Typography>
          <Typography color="text.secondary">
            {desk.left_today} of {desk.total_today} left today ·{' '}
            {formatDay(desk.today)}
            {desk.checks_due > 0 &&
              ` · ${desk.checks_due} ${desk.checks_due === 1 ? 'check' : 'checks'} due`}
          </Typography>
        </div>
        {desk.plan && (
          <Button
            variant="outlined"
            onClick={actions.replan}
            disabled={replanning}
          >
            Re-plan today
          </Button>
        )}
      </Stack>

      {active && !activeInPlan && (
        <Alert
          severity="info"
          action={
            <Button
              color="inherit"
              size="small"
              onClick={() => actions.resumeAttempt(active.id)}
            >
              Resume
            </Button>
          }
        >
          Current attempt: {active.problem_title ?? 'in progress'}
        </Alert>
      )}

      {items.length === 0 ? (
        <Alert
          severity="info"
          action={
            <Stack direction="row" spacing={1}>
              <ButtonLink to="/settings" color="inherit" size="small">
                Get the problem bank
              </ButtonLink>
              <ButtonLink to="/library" color="inherit" size="small">
                Open the library
              </ButtonLink>
            </Stack>
          }
        >
          <AlertTitle>No questions at your level yet</AlertTitle>
          {desk.bank_empty
            ? 'The LeetCode problem bank isn’t downloaded. Download it in Settings, or add problems in the library.'
            : 'Nothing fits your training levels today. Wait for checks to come due, or follow a study list.'}
        </Alert>
      ) : (
        <>
          <LaneSection
            lane="leetcode"
            items={byLane('leetcode')}
            desk={desk}
            actions={actions}
            busyItemId={busyItemId}
          />
          <LaneSection
            lane="atcoder"
            items={byLane('atcoder')}
            desk={desk}
            actions={actions}
            busyItemId={busyItemId}
          />
        </>
      )}

      {skipped.length > 0 && (
        <Accordion disableGutters variant="outlined">
          <AccordionSummary>
            <Typography>Plan changes ({skipped.length})</Typography>
          </AccordionSummary>
          <AccordionDetails>
            <List dense disablePadding>
              {skipped.map((item) => (
                <ListItem key={item.id}>
                  <ListItemText
                    primary={item.problem.title}
                    secondary={
                      item.disposition
                        ? DISPOSITION_LABEL[item.disposition]
                        : 'Skipped today'
                    }
                  />
                </ListItem>
              ))}
            </List>
          </AccordionDetails>
        </Accordion>
      )}
    </Stack>
  );
};
