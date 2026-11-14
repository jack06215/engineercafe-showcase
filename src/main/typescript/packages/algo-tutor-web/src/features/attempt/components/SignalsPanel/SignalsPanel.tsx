import Stack from '@mui/material/Stack';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';

import type { DifficultyFeel, Signals } from '@/api/types';

type Props = {
  signals: Signals;
  onChange: (patch: Partial<Signals>) => void;
  disabled?: boolean;
};

// "How did it go?" (SPEC §6.7). Clicking the chosen answer again clears it.
// They move the level classification (SPEC §7.2).
export const SignalsPanel = ({
  signals,
  onChange,
  disabled = false,
}: Props) => {
  const accepted =
    signals.accepted_first_try === null
      ? null
      : signals.accepted_first_try
        ? 'yes'
        : 'no';
  return (
    <Stack spacing={1.5} component="section" aria-label="How did it go?">
      <Typography variant="h6" component="h2">
        How did it go?
      </Typography>
      <Stack
        direction="row"
        spacing={2}
        sx={{ alignItems: 'center', flexWrap: 'wrap' }}
      >
        <Typography variant="body2">Accepted on first submission?</Typography>
        <ToggleButtonGroup
          size="small"
          exclusive
          aria-label="Accepted on first submission?"
          value={accepted}
          disabled={disabled}
          onChange={(_e, value: 'yes' | 'no' | null) =>
            onChange({
              accepted_first_try: value === null ? null : value === 'yes',
            })
          }
        >
          <ToggleButton value="yes">Yes</ToggleButton>
          <ToggleButton value="no">No</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      <Stack
        direction="row"
        spacing={2}
        sx={{ alignItems: 'center', flexWrap: 'wrap' }}
      >
        <Typography variant="body2">How did it feel?</Typography>
        <ToggleButtonGroup
          size="small"
          exclusive
          aria-label="How did it feel?"
          value={signals.difficulty}
          disabled={disabled}
          onChange={(_e, value: DifficultyFeel | null) =>
            onChange({ difficulty: value })
          }
        >
          <ToggleButton value="too_easy">Too easy</ToggleButton>
          <ToggleButton value="too_hard">Too hard</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
    </Stack>
  );
};
