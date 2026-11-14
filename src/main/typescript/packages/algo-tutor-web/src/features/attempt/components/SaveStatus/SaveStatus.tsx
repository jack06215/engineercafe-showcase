import Typography from '@mui/material/Typography';

import {
  SAVE_STATUS_LABEL,
  type SaveStatus as Status,
} from '../../hooks/useAutosave';

type Props = {
  status: Status;
};

// The autosave status line under the editor (SPEC §6.5): "Saved",
// "Unsaved changes", "Saving…" or "Not saved".
export const SaveStatus = ({ status }: Props) => {
  return (
    <Typography
      role="status"
      variant="body2"
      color={status === 'error' ? 'error' : 'text.secondary'}
    >
      {SAVE_STATUS_LABEL[status]}
    </Typography>
  );
};
