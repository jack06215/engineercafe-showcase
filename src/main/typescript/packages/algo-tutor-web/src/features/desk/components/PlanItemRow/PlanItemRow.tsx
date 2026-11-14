import MoreVertIcon from '@mui/icons-material/MoreVert';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';
import IconButton from '@mui/material/IconButton';
import ListItem from '@mui/material/ListItem';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { addDays } from 'date-fns';
import { useState } from 'react';

import type { DifficultyFeel, PlanItemOut } from '@/api/types';
import { localIsoDate } from '@/common/format';
import { RatingChip } from '@/components/ui/RatingChip';

export type PlanItemActions = {
  start: (item: PlanItemOut) => void;
  resume: (item: PlanItemOut) => void;
  makeNext: (item: PlanItemOut) => void;
  replace: (item: PlanItemOut) => void;
  postpone: (item: PlanItemOut, until: string) => void;
  skip: (item: PlanItemOut) => void;
  move: (item: PlanItemOut, by: -1 | 1) => void;
  cancel: (item: PlanItemOut) => void;
  signal: (item: PlanItemOut, feel: DifficultyFeel | null) => void;
};

type Props = {
  item: PlanItemOut;
  actions: PlanItemActions;
  // False while another attempt is unfinished (SPEC §6.1: one at a time).
  canStart: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  busy?: boolean;
  today: string;
};

export const itemState = (item: PlanItemOut) => {
  if (item.status === 'completed') return 'Done';
  if (item.status === 'skipped') return 'Skipped';
  if (item.attempt_id) return 'In progress';
  return item.status === 'active' ? 'Up next' : 'Queued';
};

// One plan row (SPEC §14 Desk): title, rating, status and reason, and its
// actions. The title isn't a link: the problem page shows topic and tags,
// which would give a transfer check away.
export const PlanItemRow = ({
  item,
  actions,
  canStart,
  canMoveUp,
  canMoveDown,
  busy = false,
  today,
}: Props) => {
  const [menu, setMenu] = useState<HTMLElement | null>(null);
  const [postponing, setPostponing] = useState(false);
  const tomorrow = localIsoDate(addDays(new Date(`${today}T00:00:00`), 1));
  const [until, setUntil] = useState(tomorrow);
  const state = itemState(item);
  const started = item.attempt_id !== null;
  const finished = item.status === 'completed';
  const unstarted = !started && !finished;
  const close = () => setMenu(null);

  return (
    <ListItem
      divider
      aria-label={item.problem.title}
      sx={{ flexWrap: 'wrap', gap: 1, alignItems: 'flex-start' }}
    >
      <Stack sx={{ flex: '1 1 16rem', minWidth: 0 }} spacing={0.5}>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <Typography component="span" sx={{ fontWeight: 600 }} noWrap>
            {item.problem.title}
          </Typography>
          <RatingChip rating={item.problem.rating} />
          <Chip
            size="small"
            label={state}
            color={state === 'In progress' ? 'primary' : 'default'}
          />
        </Stack>
        <Typography variant="body2" color="text.secondary">
          {item.reason}
        </Typography>
      </Stack>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
        {finished && item.attempt_id && (
          <ToggleButtonGroup
            size="small"
            exclusive
            aria-label="How did it feel?"
            value={item.signals?.difficulty ?? null}
            onChange={(_e, feel: DifficultyFeel | null) =>
              actions.signal(item, feel)
            }
            disabled={busy}
          >
            <ToggleButton value="too_easy">Too easy</ToggleButton>
            <ToggleButton value="too_hard">Too hard</ToggleButton>
          </ToggleButtonGroup>
        )}
        {started && !finished && (
          <Button
            variant="contained"
            size="small"
            onClick={() => actions.resume(item)}
            disabled={busy}
          >
            Resume
          </Button>
        )}
        {unstarted && (
          <Button
            variant={item.status === 'active' ? 'contained' : 'outlined'}
            size="small"
            onClick={() => actions.start(item)}
            disabled={busy || !canStart}
            title={
              canStart ? undefined : 'Finish the attempt in progress first'
            }
          >
            Start
          </Button>
        )}
        {!finished && (
          <IconButton
            size="small"
            aria-label={`More actions for ${item.problem.title}`}
            onClick={(e) => setMenu(e.currentTarget)}
            disabled={busy}
          >
            <MoreVertIcon />
          </IconButton>
        )}
      </Stack>
      <Menu anchorEl={menu} open={menu !== null} onClose={close}>
        {unstarted && item.status === 'queued' && (
          <MenuItem
            onClick={() => {
              close();
              actions.makeNext(item);
            }}
          >
            Make next
          </MenuItem>
        )}
        {canMoveUp && (
          <MenuItem
            onClick={() => {
              close();
              actions.move(item, -1);
            }}
          >
            Move up
          </MenuItem>
        )}
        {canMoveDown && (
          <MenuItem
            onClick={() => {
              close();
              actions.move(item, 1);
            }}
          >
            Move down
          </MenuItem>
        )}
        {unstarted && (
          <MenuItem
            onClick={() => {
              close();
              actions.replace(item);
            }}
          >
            Replace question
          </MenuItem>
        )}
        {unstarted && (
          <MenuItem
            onClick={() => {
              close();
              setPostponing(true);
            }}
          >
            Postpone…
          </MenuItem>
        )}
        {unstarted && (
          <MenuItem
            onClick={() => {
              close();
              actions.skip(item);
            }}
          >
            Skip today
          </MenuItem>
        )}
        {started && !finished && (
          <MenuItem
            onClick={() => {
              close();
              actions.cancel(item);
            }}
          >
            Cancel attempt
          </MenuItem>
        )}
      </Menu>
      <Dialog open={postponing} onClose={() => setPostponing(false)}>
        <DialogTitle>Postpone {item.problem.title}</DialogTitle>
        <DialogContent>
          <TextField
            type="date"
            label="Until"
            value={until}
            onChange={(e) => setUntil(e.target.value)}
            slotProps={{
              inputLabel: { shrink: true },
              htmlInput: { min: tomorrow },
            }}
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPostponing(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!until || until < tomorrow}
            onClick={() => {
              setPostponing(false);
              actions.postpone(item, until);
            }}
          >
            Postpone
          </Button>
        </DialogActions>
      </Dialog>
    </ListItem>
  );
};
