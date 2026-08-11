/**
 * HttpClient.getPage regression tests — PR-1 Fix 3.
 *
 * A collection endpoint is contractually required to return a
 * `CollectionEnvelope`. Previously `getPage` masked a `204`/empty body as a fake
 * empty envelope, making a contract violation indistinguishable from a
 * legitimately empty collection and hiding a missing parent behind `[]`.
 *
 * These tests pin the corrected behaviour:
 *   - `200 {"data":[],...}` (legitimately empty) → returned as-is.
 *   - `204` / empty `200` body → `UnexpectedHttpError` (no masking).
 *   - `404` → `NotFoundError` (parent missing, never `[]`).
 */

import { describe, expect, it } from "vitest";

import { HttpClient } from "../src/http-client";
import { NotFoundError, UnexpectedHttpError } from "../src/errors";
import { createSessionManager } from "../src/session";

function makeClient(respond: (url: string) => Response): HttpClient {
  const fetchImpl = ((input: RequestInfo | URL) =>
    Promise.resolve(
      respond(input instanceof URL ? input.toString() : String(input)),
    )) as unknown as typeof fetch;
  const session = createSessionManager({
    baseUrl: "http://test.local",
    fetchImpl,
  });
  return new HttpClient({
    baseUrl: "http://test.local",
    fetchImpl,
    session,
  });
}

const EMPTY_COLLECTION_BODY = JSON.stringify({
  data: [],
  page: { next_cursor: null, has_more: false },
});

describe("HttpClient.getPage — empty-response contract", () => {
  it("returns a legitimately empty 200 collection envelope as-is", async () => {
    const client = makeClient(
      () => new Response(EMPTY_COLLECTION_BODY, { status: 200 }),
    );
    const env = await client.getPage<unknown>("/api/runs/r1/events");
    expect(env.data).toEqual([]);
    expect(env.page?.has_more).toBe(false);
    expect(env.page?.next_cursor).toBeNull();
  });

  it("throws UnexpectedHttpError on 204 (no content)", async () => {
    const client = makeClient(() => new Response(null, { status: 204 }));
    await expect(
      client.getPage<unknown>("/api/runs/r1/events"),
    ).rejects.toMatchObject({ name: UnexpectedHttpError.name, status: 204 });
  });

  it("throws UnexpectedHttpError on 200 with an empty body", async () => {
    const client = makeClient(() => new Response("", { status: 200 }));
    await expect(
      client.getPage<unknown>("/api/runs/r1/events"),
    ).rejects.toMatchObject({ name: UnexpectedHttpError.name, status: 200 });
  });

  it("throws NotFoundError on 404 instead of returning an empty list", async () => {
    const client = makeClient(
      () =>
        new Response(
          JSON.stringify({
            type: "https://xingwen.example/errors/not_found",
            title: "Resource not found",
            status: 404,
            detail: "Run not found",
            code: "NOT_FOUND",
          }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        ),
    );
    await expect(
      client.getPage<unknown>("/api/runs/r1/events"),
    ).rejects.toBeInstanceOf(NotFoundError);
  });
});

describe("HttpClient.list — empty-response contract", () => {
  it.each([
    [204, () => new Response(null, { status: 204 })],
    [200, () => new Response("", { status: 200 })],
  ])("throws UnexpectedHttpError with status %i", async (status, respond) => {
    const client = makeClient(respond);
    await expect(client.list<unknown>("/api/projects")).rejects.toMatchObject({
      name: UnexpectedHttpError.name,
      status,
    });
  });

  it("throws NotFoundError on 404 instead of returning an empty list", async () => {
    const client = makeClient(
      () =>
        new Response(
          JSON.stringify({
            title: "Resource not found",
            status: 404,
            detail: "Parent not found",
            code: "NOT_FOUND",
          }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        ),
    );
    await expect(client.list<unknown>("/api/projects")).rejects.toBeInstanceOf(
      NotFoundError,
    );
  });
});
