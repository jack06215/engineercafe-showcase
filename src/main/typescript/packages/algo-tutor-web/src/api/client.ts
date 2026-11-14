// The algo_tutor HTTP client (SPEC §15): JSON over /api, which Vite forwards
// to the API in development and the API serves itself once the UI is built.
// Endpoint functions are written against it per feature; this file owns the
// wire rules they all share.

export const API_BASE = '/api';

// SPEC §18.1. Known codes, plus whatever a newer server sends.
export type ErrorCode =
  | 'VALIDATION'
  | 'NOT_FOUND'
  | 'STALE'
  | 'ACTIVE_ATTEMPT'
  | 'COMPLETED'
  | 'IDEMPOTENCY_MISMATCH'
  | 'NO_REPLACEMENT'
  | 'GAP_DECISION'
  | 'SOLUTION_FILE_MISSING'
  | 'SOLUTION_PATH_INVALID'
  | 'HIDDEN_ASSESSMENT'
  | 'NOT_LOCAL'
  | 'TUTOR_UNAVAILABLE'
  // No JSON error body: the API is down, or something in between answered.
  | 'UNREACHABLE'
  | (string & {});

// A failed request: the server's `{ "error": { "code", "message" } }`, or
// UNREACHABLE when there was no such body.
export class ApiError extends Error {
  readonly status: number;
  readonly code: ErrorCode;
  // TUTOR_UNAVAILABLE's reason (SPEC §12.1): disabled, unavailable, …
  readonly kind: string | null;

  constructor(
    status: number,
    code: ErrorCode,
    message: string,
    kind: string | null = null,
  ) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.kind = kind;
  }
}

export const isApiError = (
  error: unknown,
  code?: ErrorCode,
): error is ApiError =>
  error instanceof ApiError && (code === undefined || error.code === code);

// A fresh key for one logical write (finish, rebuild, pack import; SPEC
// §18.2). Make it once per user action and reuse it on retries, so a retry
// after a lost response replays the first result instead of acting twice.
export const newIdempotencyKey = (): string => crypto.randomUUID();

type Method = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

export type RequestOptions = {
  body?: unknown;
  idempotencyKey?: string;
  query?: Record<string, string | number | boolean | null | undefined>;
  signal?: AbortSignal;
};

const UNREACHABLE_MESSAGE =
  "Can't reach the algo_tutor API. Start it with `bazel run //packages/algo_tutor:serve`.";

const withQuery = (path: string, query: RequestOptions['query']): string => {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) params.set(name, String(value));
  }
  const text = params.toString();
  return text ? `${path}?${text}` : path;
};

const readError = async (response: Response): Promise<ApiError> => {
  const data: unknown = await response.json().catch(() => null);
  const error =
    data && typeof data === 'object' && 'error' in data
      ? (data as { error: unknown }).error
      : null;
  if (error && typeof error === 'object') {
    const { code, message, kind } = error as Record<string, unknown>;
    if (typeof code === 'string' && typeof message === 'string') {
      return new ApiError(
        response.status,
        code,
        message,
        typeof kind === 'string' ? kind : null,
      );
    }
  }
  return new ApiError(
    response.status,
    'UNREACHABLE',
    response.status >= 500 ? UNREACHABLE_MESSAGE : response.statusText,
  );
};

export async function request<T>(
  method: Method,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  // Every write is JSON, body or not: the API refuses other content types
  // so a cross-site form post can't reach it (SPEC §15).
  if (method !== 'GET') headers['Content-Type'] = 'application/json';
  if (options.idempotencyKey) {
    headers['Idempotency-Key'] = options.idempotencyKey;
  }

  let response: Response;
  try {
    response = await fetch(API_BASE + withQuery(path, options.query), {
      method,
      headers,
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') {
      throw cause;
    }
    throw new ApiError(0, 'UNREACHABLE', UNREACHABLE_MESSAGE);
  }

  if (!response.ok) throw await readError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, 'body'>) =>
    request<T>('GET', path, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>('POST', path, { ...options, body }),
  patch: <T>(path: string, body: unknown, options?: RequestOptions) =>
    request<T>('PATCH', path, { ...options, body }),
  delete: <T = void>(path: string, options?: RequestOptions) =>
    request<T>('DELETE', path, options),
};
