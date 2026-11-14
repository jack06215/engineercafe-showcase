import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { useEasyQuery } from '@/hooks/useEasyQuery';

const wrapper = ({ children }: { children: React.ReactNode }) => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
};

describe('useEasyQuery', () => {
  it('is loading, then succeeds with the data', async () => {
    const { result } = renderHook(
      () => useEasyQuery(['answer'], () => Promise.resolve(42)),
      { wrapper },
    );

    expect(result.current).toEqual({ status: 'isLoading' });
    await waitFor(() => {
      expect(result.current).toEqual({ status: 'isSuccess', data: 42 });
    });
  });

  it('treats a falsy result as data, not an error', async () => {
    const { result } = renderHook(
      () => useEasyQuery(['zero'], () => Promise.resolve(0)),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current).toEqual({ status: 'isSuccess', data: 0 });
    });
  });

  it('reports the error a query throws', async () => {
    const error = new Error('boom');
    const { result } = renderHook(
      () => useEasyQuery(['fails'], () => Promise.reject(error)),
      { wrapper },
    );

    await waitFor(() => {
      expect(result.current).toEqual({ status: 'isError', error });
    });
  });
});
