import PauseIcon from '@mui/icons-material/Pause';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { formatMmSs } from '@/common/time';

type Props = {
  seconds: number;
  running: boolean;
  paused: boolean;
  // A gap over 120 s paused it; Resume needs "count this gap?" answered.
  gapPending: boolean;
  gapSeconds: number;
  onPause: () => void;
  onResume: (includeGap?: boolean) => void;
  // While a write is frozen (an error is showing).
  disabled?: boolean;
};

// The attempt page's stopwatch (SPEC §6.3): the running time, Pause and
// Resume, and the "Paused" banner with the gap question.
export const Stopwatch = ({
  seconds,
  running,
  paused,
  gapPending,
  gapSeconds,
  onPause,
  onResume,
  disabled = false,
}: Props) => {
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
        <Typography
          component="span"
          variant="h5"
          aria-label="Active time"
          sx={{ fontVariantNumeric: 'tabular-nums' }}
        >
          {formatMmSs(seconds)}
        </Typography>
        {running ? (
          <Button
            size="small"
            startIcon={<PauseIcon />}
            onClick={onPause}
            disabled={disabled}
          >
            Pause
          </Button>
        ) : (
          !gapPending && (
            <Button
              size="small"
              startIcon={<PlayArrowIcon />}
              onClick={() => onResume()}
              disabled={disabled || !paused}
            >
              Resume
            </Button>
          )
        )}
      </Stack>
      {gapPending ? (
        <Alert
          severity="info"
          action={
            <Stack direction="row" spacing={1}>
              <Button
                size="small"
                color="inherit"
                onClick={() => onResume(true)}
                disabled={disabled}
              >
                Count it
              </Button>
              <Button
                size="small"
                color="inherit"
                onClick={() => onResume(false)}
                disabled={disabled}
              >
                Don't count it
              </Button>
            </Stack>
          }
        >
          Paused: this page went quiet for {formatMmSs(gapSeconds)} (the laptop
          slept or the tab was closed). Count this gap?
        </Alert>
      ) : (
        paused && <Alert severity="info">Paused</Alert>
      )}
    </Stack>
  );
};
