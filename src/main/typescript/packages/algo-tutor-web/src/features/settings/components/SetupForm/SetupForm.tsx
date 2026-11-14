import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Checkbox from '@mui/material/Checkbox';
import FormControl from '@mui/material/FormControl';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormLabel from '@mui/material/FormLabel';
import Paper from '@mui/material/Paper';
import Radio from '@mui/material/Radio';
import RadioGroup from '@mui/material/RadioGroup';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useState } from 'react';

import type { BundledSet, SetupIn, SetupState } from '@/api/types';

type Props = {
  state: SetupState;
  onSubmit: (body: SetupIn) => Promise<void>;
};

const COURSES: [BundledSet | 'none', string][] = [
  ['none', 'None'],
  ['neetcode-150', 'NeetCode 150'],
  ['blind-75', 'Blind 75'],
  ['hello-interview', 'Hello Interview'],
];

// Setup (SPEC §14): shown until it's done.
export const SetupForm = ({ state, onSubmit }: Props) => {
  const [perDay, setPerDay] = useState(String(state.questions_per_day));
  const [download, setDownload] = useState(true);
  const [follow, setFollow] = useState<BundledSet | 'none'>('none');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const count = Number(perDay);
  const valid = Number.isInteger(count) && count >= 1 && count <= 20;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        questions_per_day: count,
        download_bank: download,
        follow: follow === 'none' ? null : follow,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <Paper variant="outlined" sx={{ p: 3, maxWidth: 560, mx: 'auto', mt: 6 }}>
      <Stack
        component="form"
        spacing={2.5}
        aria-label="Set up algo_tutor"
        onSubmit={(e: React.FormEvent) => void submit(e)}
      >
        <Typography variant="h4" component="h1">
          Set up algo_tutor
        </Typography>
        <Typography color="text.secondary">
          Solve on LeetCode or AtCoder, then record how it went here. algo_tutor
          plans each day and brings ideas back for review. The AI tutor is
          optional.
        </Typography>
        <TextField
          type="number"
          label="Questions per day"
          value={perDay}
          onChange={(e) => setPerDay(e.target.value)}
          error={!valid}
          helperText="1–20; you can change it in Settings"
          slotProps={{ htmlInput: { min: 1, max: 20 } }}
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={download}
              onChange={(e) => setDownload(e.target.checked)}
            />
          }
          label="Download the LeetCode problem bank now"
        />
        <FormControl>
          <FormLabel id="follow-label">Follow a course</FormLabel>
          <RadioGroup
            aria-labelledby="follow-label"
            value={follow}
            onChange={(e) => setFollow(e.target.value as BundledSet | 'none')}
          >
            {COURSES.map(([value, label]) => (
              <FormControlLabel
                key={value}
                value={value}
                control={<Radio />}
                label={label}
              />
            ))}
          </RadioGroup>
        </FormControl>
        <Typography variant="body2" color="text.secondary">
          Timezone: {state.timezone}
        </Typography>
        {error && <Alert severity="error">{error}</Alert>}
        <div>
          <Button type="submit" variant="contained" disabled={busy || !valid}>
            Start
          </Button>
        </div>
      </Stack>
    </Paper>
  );
};
