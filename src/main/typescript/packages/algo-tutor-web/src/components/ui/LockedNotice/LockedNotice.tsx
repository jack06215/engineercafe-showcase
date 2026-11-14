import LockOutlinedIcon from '@mui/icons-material/LockOutlined';
import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Button from '@mui/material/Button';
import { createLink } from '@tanstack/react-router';

const ButtonLink = createLink(Button);

// SPEC §9: while a hidden assessment runs, pages that could give the
// problem's idea away are locked. Not an error: finishing unlocks them.
export const LockedNotice = () => (
  <Alert
    severity="info"
    icon={<LockOutlinedIcon />}
    action={
      <ButtonLink to="/" color="inherit" size="small">
        Back to the desk
      </ButtonLink>
    }
  >
    <AlertTitle>Locked during your assessment</AlertTitle>
    This page could give the approach away. It opens again once you finish the
    assessment.
  </Alert>
);
