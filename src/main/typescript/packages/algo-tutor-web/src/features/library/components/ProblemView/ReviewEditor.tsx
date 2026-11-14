import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';

import type { ReviewAction, ReviewPatch, ReviewTargetOut } from '@/api/types';
import {
  formatDay,
  REVIEW_ACTION_LABEL,
  REVIEW_STAGE_LABEL,
} from '@/common/format';

type Props = {
  review: ReviewTargetOut;
  // A never-attempted problem's target takes only a snooze.
  attempted: boolean;
  onSave: (patch: ReviewPatch) => Promise<void>;
};

const ACTIONS: ReviewAction[] = ['recommended', 'manual', 'snooze', 'none'];

// The review schedule editor (SPEC §8.2): the recommended date, a date you
// choose, a snooze, or no review.
export const ReviewEditor = ({ review, attempted, onSave }: Props) => {
  const [action, setAction] = useState<ReviewAction>(review.action);
  const [date, setDate] = useState(
    review.action === 'manual' || review.action === 'snooze'
      ? (review.effective_date ?? '')
      : '',
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const needsDate = action === 'manual' || action === 'snooze';

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await onSave({
        version: review.version,
        action,
        review_date: needsDate ? date : null,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack spacing={1.5}>
      <Typography variant="body2">
        {review.effective_date
          ? `Next review ${formatDay(review.effective_date)}`
          : 'No scheduled review'}{' '}
        · stage: {REVIEW_STAGE_LABEL[review.stage]}
        {review.recommended_date &&
          review.action !== 'recommended' &&
          ` · recommended ${formatDay(review.recommended_date)}`}
      </Typography>
      <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap' }}>
        <TextField
          select
          size="small"
          label="Schedule"
          value={action}
          onChange={(e) => setAction(e.target.value as ReviewAction)}
          sx={{ minWidth: 220 }}
        >
          {ACTIONS.filter(
            (a) => attempted || a === 'snooze' || a === review.action,
          ).map((a) => (
            <MenuItem key={a} value={a}>
              {REVIEW_ACTION_LABEL[a]}
            </MenuItem>
          ))}
        </TextField>
        {needsDate && (
          <TextField
            type="date"
            size="small"
            label={action === 'snooze' ? 'Snooze until' : 'Review on'}
            value={date}
            onChange={(e) => setDate(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
          />
        )}
        <Button
          variant="outlined"
          onClick={() => void save()}
          disabled={busy || (needsDate && date === '')}
        >
          Save schedule
        </Button>
      </Stack>
      {error && <Alert severity="error">{error}</Alert>}
    </Stack>
  );
};
