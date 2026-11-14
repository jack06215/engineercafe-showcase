import { afterEach, describe, expect, it, vi } from 'vitest';

import { api, ApiError, isApiError, newIdempotencyKey } from './client';

type Call = [string, RequestInit];

const stubFetch = (response: Response | Error) => {
  const fetchMock = vi.fn<
    (url: string, init: RequestInit) => Promise<Response>
  >(() =>
    response instanceof Error
      ? Promise.reject(response)
      : Promise.resolve(response),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
};

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('api client', () => {
  it('GETs JSON under /api with the query string, without a content type', async () => {
    const fetchMock = stubFetch(json(200, { ok: true }));

    await expect(
      api.get('/problems', {
        query: { q: 'two sum', page: 2, topic: undefined, paid: null },
      }),
    ).resolves.toEqual({ ok: true });

    const [url, init] = fetchMock.mock.calls[0] as Call;
    expect(url).toBe('/api/problems?q=two+sum&page=2');
    expect(init.method).toBe('GET');
    expect(init.headers).not.toHaveProperty('Content-Type');
    expect(init.body).toBeUndefined();
  });

  it('sends writes as JSON with the idempotency key', async () => {
    const fetchMock = stubFetch(json(200, { id: 'a1' }));

    await api.post(
      '/attempts/a1/finish',
      { version: 3 },
      { idempotencyKey: 'key-1' },
    );

    const [url, init] = fetchMock.mock.calls[0] as Call;
    expect(url).toBe('/api/attempts/a1/finish');
    expect(init.method).toBe('POST');
    expect(init.headers).toMatchObject({
      'Content-Type': 'application/json',
      'Idempotency-Key': 'key-1',
    });
    expect(init.body).toBe('{"version":3}');
  });

  it('marks a bodyless DELETE as JSON too, and returns nothing on 204', async () => {
    const fetchMock = stubFetch(new Response(null, { status: 204 }));

    await expect(api.delete('/attempts/a1')).resolves.toBeUndefined();

    const [, init] = fetchMock.mock.calls[0] as Call;
    expect(init.headers).toMatchObject({ 'Content-Type': 'application/json' });
  });

  it("turns the server's error body into an ApiError", async () => {
    stubFetch(
      json(409, {
        error: { code: 'STALE', message: 'Attempt changed elsewhere' },
      }),
    );

    const error = await api
      .patch('/attempts/a1/draft', { version: 1 })
      .catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 409,
      code: 'STALE',
      message: 'Attempt changed elsewhere',
      kind: null,
    });
    expect(isApiError(error, 'STALE')).toBe(true);
    expect(isApiError(error, 'COMPLETED')).toBe(false);
  });

  it("keeps the tutor's error kind", async () => {
    stubFetch(
      json(503, {
        error: {
          code: 'TUTOR_UNAVAILABLE',
          message: 'Ollama is not running',
          kind: 'unavailable',
        },
      }),
    );

    await expect(api.post('/tutor/test')).rejects.toMatchObject({
      code: 'TUTOR_UNAVAILABLE',
      kind: 'unavailable',
    });
  });

  it('reports UNREACHABLE when the API is down', async () => {
    stubFetch(new TypeError('Failed to fetch'));
    await expect(api.get('/health')).rejects.toMatchObject({
      status: 0,
      code: 'UNREACHABLE',
    });

    // Vite's proxy answers 502 with no JSON body while the API is stopped.
    stubFetch(new Response('Bad Gateway', { status: 502 }));
    await expect(api.get('/health')).rejects.toMatchObject({
      status: 502,
      code: 'UNREACHABLE',
    });
  });

  it('makes a distinct idempotency key each time', () => {
    const first = newIdempotencyKey();
    expect(first).toMatch(/^[A-Za-z0-9_.:-]{1,200}$/);
    expect(newIdempotencyKey()).not.toBe(first);
  });
});
