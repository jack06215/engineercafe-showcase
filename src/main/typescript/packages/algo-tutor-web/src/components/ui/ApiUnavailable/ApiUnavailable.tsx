import Alert from '@mui/material/Alert';
import AlertTitle from '@mui/material/AlertTitle';
import Button from '@mui/material/Button';

import { isApiError } from '@/api/client';

type Props = {
  error: unknown;
  onRetry?: () => void;
};

// A request failed. When the API isn't answering at all, say how to start
// it (SPEC §3.1: the PoC runs the API and the UI as two processes).
export const ApiUnavailable = ({ error, onRetry }: Props) => {
  const unreachable = !isApiError(error) || error.code === 'UNREACHABLE';
  return (
    <Alert
      severity="error"
      action={
        onRetry && (
          <Button color="inherit" size="small" onClick={onRetry}>
            Try again
          </Button>
        )
      }
    >
      <AlertTitle>
        {unreachable
          ? "Can't reach the algo_tutor API"
          : 'Something went wrong'}
      </AlertTitle>
      {unreachable ? (
        <>
          Start it with <code>bazel run //packages/algo_tutor:serve</code>, then
          try again.
        </>
      ) : (
        (error as Error).message
      )}
    </Alert>
  );
};
