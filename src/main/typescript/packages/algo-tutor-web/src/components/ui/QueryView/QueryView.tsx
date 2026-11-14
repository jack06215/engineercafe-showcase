import LinearProgress from '@mui/material/LinearProgress';

import { isApiError } from '@/api/client';

import { ApiUnavailable } from '../ApiUnavailable';
import { LockedNotice } from '../LockedNotice';

import type { UseQueryResult } from '@tanstack/react-query';

type Props<T> = {
  query: UseQueryResult<T>;
  children: (data: T) => React.ReactNode;
};

// A query's three states: loading, failed (or locked by the hidden
// assessment, SPEC §9), or its data.
export const QueryView = <T,>({ query, children }: Props<T>) => {
  if (query.isPending) return <LinearProgress aria-label="Loading" />;
  if (query.isError) {
    if (isApiError(query.error, 'HIDDEN_ASSESSMENT')) return <LockedNotice />;
    return (
      <ApiUnavailable
        error={query.error}
        onRetry={() => void query.refetch()}
      />
    );
  }
  return <>{children(query.data)}</>;
};
