import Autocomplete from '@mui/material/Autocomplete';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';

import type { PatternSummary } from '@/api/types';

type Props = {
  // Pattern ids on the problem.
  value: string[];
  options: PatternSummary[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
  title?: string;
};

// Pattern labels on a problem (SPEC §5.8): added by hand, never guessed.
// Used on the problem page and a finished attempt.
export const PatternPicker = ({
  value,
  options,
  onChange,
  disabled = false,
  title = 'Patterns',
}: Props) => {
  const byId = new Map(options.map((p) => [p.id, p]));
  return (
    <Stack spacing={1} component="section" aria-label={title}>
      <Typography variant="h6" component="h2">
        {title}
      </Typography>
      <Autocomplete
        multiple
        size="small"
        disabled={disabled}
        options={options.map((p) => p.id)}
        value={value}
        getOptionLabel={(id) => byId.get(id)?.name ?? id}
        onChange={(_e, ids) => onChange(ids)}
        renderInput={(params) => (
          <TextField {...params} label="Pattern labels" />
        )}
      />
    </Stack>
  );
};
