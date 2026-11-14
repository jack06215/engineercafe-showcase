import { type QueryKey, useQuery } from '@tanstack/react-query';

export type Result<T> =
  | { status: 'isLoading' }
  | { status: 'isError'; error: unknown }
  | { status: 'isSuccess'; data: T };

// Needs a QueryClientProvider above it (AppProviders).
export const useEasyQuery = <T>(
  key: QueryKey,
  query: () => Promise<T>,
): Result<T> => {
  const result = useQuery({
    queryKey: key,
    queryFn: () => query(),
  });

  // TanStack Query 5's `isPending` (no data yet) is what 4's `isLoading`
  // meant; 5's `isLoading` is false while a query waits offline.
  if (result.isPending) return { status: 'isLoading' };
  if (result.isError) return { status: 'isError', error: result.error };
  return {
    status: 'isSuccess',
    data: result.data,
  };
};
