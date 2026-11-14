import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import FormControl from '@mui/material/FormControl';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormHelperText from '@mui/material/FormHelperText';
import FormLabel from '@mui/material/FormLabel';
import MenuItem from '@mui/material/MenuItem';
import Radio from '@mui/material/Radio';
import RadioGroup from '@mui/material/RadioGroup';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';

import type {
  FinishIn,
  Help,
  HintLevel,
  Outcome,
  ReviewChoice,
} from '@/api/types';
import { HELP_LABEL, OUTCOME_LABEL } from '@/common/format';
import { formatMmSs, MM_SS_PATTERN } from '@/common/time';

// Everything but the version and the draft (code, notes, language), which
// the page adds.
export type FinishValues = Pick<
  FinishIn,
  'outcome' | 'help' | 'time' | 'confidence' | 'review_choice' | 'review_date'
>;

type Props = {
  // The stopwatch's time, the Time field's default until it's edited.
  stopwatchSeconds: number;
  // The strongest hint Algo-chan gave, Help's default until it's edited.
  strongestHint: HintLevel | null;
  // SPEC §6.6: the code must be non-empty.
  hasCode: boolean;
  onSubmit: (values: FinishValues) => Promise<void>;
  disabled?: boolean;
};

const HELPS: Help[] = ['unknown', 'none', 'small', 'major', 'solution'];
const OUTCOMES: Outcome[] = ['solved', 'not_solved', 'stopped'];

// The result form (SPEC §6.6).
export const FinishForm = ({
  stopwatchSeconds,
  strongestHint,
  hasCode,
  onSubmit,
  disabled = false,
}: Props) => {
  const [outcome, setOutcome] = useState<Outcome>('solved');
  const [help, setHelp] = useState<Help | null>(null);
  const [time, setTime] = useState<string | null>(null);
  const [confidence, setConfidence] = useState<number | null>(null);
  const [reviewChoice, setReviewChoice] = useState<ReviewChoice>('recommended');
  const [reviewDate, setReviewDate] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Untouched fields follow the stopwatch and Algo-chan's hints.
  const shownHelp: Help = help ?? strongestHint ?? 'unknown';
  const shownTime = time ?? formatMmSs(stopwatchSeconds);
  const timeValid = MM_SS_PATTERN.test(shownTime.trim());
  const dateMissing = reviewChoice === 'manual' && reviewDate === '';
  const valid = hasCode && timeValid && !dateMissing;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitted(true);
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        outcome,
        help: shownHelp,
        time: shownTime.trim(),
        confidence,
        review_choice: reviewChoice,
        review_date: reviewChoice === 'manual' ? reviewDate : null,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack
      component="form"
      aria-label="Finish the attempt"
      spacing={2}
      noValidate
      onSubmit={(e: React.FormEvent) => void submit(e)}
    >
      <Typography variant="h6" component="h2">
        Finish
      </Typography>
      <Typography variant="body2" color="text.secondary">
        Submit on the judge, then record how it went. An unfinished solution
        still counts as practice.
      </Typography>

      <FormControl>
        <FormLabel id="outcome-label">Outcome</FormLabel>
        <RadioGroup
          row
          aria-labelledby="outcome-label"
          value={outcome}
          onChange={(e) => setOutcome(e.target.value as Outcome)}
        >
          {OUTCOMES.map((value) => (
            <FormControlLabel
              key={value}
              value={value}
              control={<Radio size="small" />}
              label={OUTCOME_LABEL[value]}
            />
          ))}
        </RadioGroup>
      </FormControl>

      <TextField
        select
        size="small"
        label="Help used"
        value={shownHelp}
        onChange={(e) => setHelp(e.target.value as Help)}
        helperText="Leaving Help as Unknown schedules a repair tomorrow"
      >
        {HELPS.map((value) => (
          <MenuItem key={value} value={value}>
            {HELP_LABEL[value]}
          </MenuItem>
        ))}
      </TextField>

      <TextField
        size="small"
        label="Time (mm:ss)"
        value={shownTime}
        onChange={(e) => setTime(e.target.value)}
        error={submitted && !timeValid}
        helperText={
          submitted && !timeValid
            ? 'Minutes, a colon and two-digit seconds, e.g. 12:34'
            : 'From the stopwatch until you change it'
        }
        required
      />

      <TextField
        select
        size="small"
        label="Confidence"
        value={confidence === null ? '' : String(confidence)}
        onChange={(e) =>
          setConfidence(e.target.value === '' ? null : Number(e.target.value))
        }
        slotProps={{
          select: { displayEmpty: true },
          inputLabel: { shrink: true },
        }}
      >
        <MenuItem value="">Not rated</MenuItem>
        {[1, 2, 3, 4, 5].map((n) => (
          <MenuItem key={n} value={String(n)}>
            {n}
          </MenuItem>
        ))}
      </TextField>

      <FormControl>
        <FormLabel id="review-label">Next review</FormLabel>
        <RadioGroup
          aria-labelledby="review-label"
          value={reviewChoice}
          onChange={(e) => setReviewChoice(e.target.value as ReviewChoice)}
        >
          <FormControlLabel
            value="recommended"
            control={<Radio size="small" />}
            label="Use the recommended date"
          />
          <FormControlLabel
            value="manual"
            control={<Radio size="small" />}
            label="Choose a date"
          />
          <FormControlLabel
            value="none"
            control={<Radio size="small" />}
            label="No scheduled review"
          />
        </RadioGroup>
        {reviewChoice === 'manual' && (
          <TextField
            type="date"
            size="small"
            label="Review on"
            value={reviewDate}
            onChange={(e) => setReviewDate(e.target.value)}
            error={submitted && dateMissing}
            slotProps={{ inputLabel: { shrink: true } }}
            sx={{ mt: 1, maxWidth: 220 }}
          />
        )}
        {submitted && dateMissing && (
          <FormHelperText error>Pick the review date.</FormHelperText>
        )}
      </FormControl>

      {submitted && !hasCode && (
        <Alert severity="warning">
          Paste or write your solution code first, or link its file.
        </Alert>
      )}
      {error && <Alert severity="error">{error}</Alert>}

      <div>
        <Button type="submit" variant="contained" disabled={disabled || busy}>
          {busy ? 'Saving…' : 'Save result'}
        </Button>
      </div>
    </Stack>
  );
};
