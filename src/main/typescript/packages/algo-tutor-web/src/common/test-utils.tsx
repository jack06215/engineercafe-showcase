import { ThemeProvider } from '@mui/material/styles';
import { QueryClient } from '@tanstack/react-query';
import {
  createMemoryHistory,
  createRootRoute,
  createRouter,
  RouterProvider,
} from '@tanstack/react-router';
import {
  queries,
  type Queries,
  render,
  type RenderOptions,
} from '@testing-library/react';
import { vi } from 'vitest';

import App from '@/App';
import { AppProviders } from '@/common/providers';
import { createAppRouter } from '@/common/router';
import { theme } from '@/common/theme';

// The whole app at `path`: its providers and its real route tree, on an
// in-memory history, with a fresh query cache and no retries so a failing
// query fails the test at once. Route components are code-split and load
// asynchronously, so query with `findBy…` first.
export function routeRender(path = '/') {
  const router = createAppRouter({
    history: createMemoryHistory({ initialEntries: [path] }),
  });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return {
    router,
    ...render(<App router={router} queryClient={queryClient} />),
  };
}

// One component inside the app's providers and a single-route router, for
// components that use router hooks (links, leave guards).
export function routeRenderComponent(ui: React.ReactElement) {
  const router = createRouter({
    routeTree: createRootRoute({ component: () => ui }),
    history: createMemoryHistory({ initialEntries: ['/'] }),
  });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
}

const ThemeWrapper: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
};

// A single component with only the theme around it.
export function themeRender<
  Q extends Queries = typeof queries,
  Container extends Element | DocumentFragment = HTMLElement,
  BaseElement extends Element | DocumentFragment = Container,
>(ui: React.ReactElement, options?: RenderOptions<Q, Container, BaseElement>) {
  return render(ui, { wrapper: ThemeWrapper, ...options });
}

export type FakeRequest = {
  method: string;
  path: string;
  query: URLSearchParams;
  body: unknown;
  headers: Record<string, string>;
};

// A route's answer: a value (sent as JSON with 200), a Response, or a
// function of the request returning either.
type Route = unknown | ((request: FakeRequest) => unknown);

// An error body as the API sends it (SPEC §18.1).
export const apiErrorResponse = (
  status: number,
  code: string,
  message = code,
  kind?: string,
) =>
  new Response(JSON.stringify({ error: { code, message, kind } }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

// A fake of the API on `fetch`. Routes are keyed `'METHOD /path'` or just
// `'/path'` (any method), under /api; anything else is a 404. `calls`
// records every request, in order.
export function fakeApi(routes: Record<string, Route>) {
  const calls: FakeRequest[] = [];
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://127.0.0.1:5173');
      const method = init?.method ?? 'GET';
      const request: FakeRequest = {
        method,
        path: url.pathname.replace(/^\/api/, ''),
        query: url.searchParams,
        body:
          typeof init?.body === 'string' ? JSON.parse(init.body) : undefined,
        headers: (init?.headers ?? {}) as Record<string, string>,
      };
      calls.push(request);
      const key = `${method} ${request.path}`;
      const route = key in routes ? routes[key] : routes[request.path];
      if (route === undefined && !(request.path in routes)) {
        return apiErrorResponse(404, 'NOT_FOUND', `${key} not found`);
      }
      const answer =
        typeof route === 'function'
          ? (route as (r: FakeRequest) => unknown)(request)
          : route;
      // A Response body reads once; hand out copies so a route can repeat.
      if (answer instanceof Response) return answer.clone();
      if (answer === undefined) return new Response(null, { status: 204 });
      return new Response(JSON.stringify(answer), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    },
  );
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, calls };
}

// Answers requests from `responses`, keyed by path under /api (`'/setup'`).
export function stubApi(responses: Record<string, unknown>) {
  return fakeApi(responses).fetchMock;
}
