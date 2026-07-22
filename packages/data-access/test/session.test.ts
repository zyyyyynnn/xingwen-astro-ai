/**
 * Session manager tests — anonymous session lifecycle and CSRF handling.
 *
 * Covers: session creation via POST /api/v2/sessions, CSRF token retrieval,
 * session revocation via DELETE, session-expired notification, session reuse
 * on repeated ensureSession, and CSRF attachment to non-safe methods.
 */

import { http, HttpResponse } from "msw";
import { expect, it } from "vitest";

import { createSessionManager } from "../src/session";

import {
  createSessionManagerForTest,
  defaultHandlers,
  httpServer,
  problem,
  TEST_BASE_URL,
} from "./http-helpers";

it("ensureSession creates a session and stores CSRF token", async () => {
  httpServer.use(...defaultHandlers);
  const session = createSessionManagerForTest();
  const info = await session.ensureSession();
  expect(info.sessionId).toBe("sess_01JEXAMPLE");
  expect(info.csrfToken).toBe("csrf_test_token");
  expect(info.expiresAt).toBe("2026-07-21T09:00:00Z");
  expect(info.quota.runsPerDay).toBe(50);
  expect(info.quota.sharesPerHour).toBe(20);
  expect(info.quota.feedbacksPerHour).toBe(30);
  expect(session.getCurrent()).toBe(info);
});

it("ensureSession reuses the existing session on repeated calls", async () => {
  httpServer.use(...defaultHandlers);
  const session = createSessionManagerForTest();
  const first = await session.ensureSession();
  const second = await session.ensureSession();
  expect(second).toBe(first);
  // Only one POST /sessions should have been issued; MSW would log an
  // unhandled request if a second POST arrived, but since the handler is
  // still registered we instead assert referential equality.
  expect(session.getCurrent()).toBe(first);
});

it("revokeSession clears the current session and returns 204", async () => {
  httpServer.use(...defaultHandlers);
  const session = createSessionManagerForTest();
  await session.ensureSession();
  expect(session.getCurrent()).not.toBeNull();
  await session.revokeSession();
  expect(session.getCurrent()).toBeNull();
});

it("revokeSession is a no-op when no session exists", async () => {
  httpServer.use(...defaultHandlers);
  const session = createSessionManagerForTest();
  // No ensureSession called; revokeSession should not throw.
  await expect(session.revokeSession()).resolves.toBeUndefined();
  expect(session.getCurrent()).toBeNull();
});

it("notifyExpired clears the session and notifies listeners", async () => {
  httpServer.use(...defaultHandlers);
  const session = createSessionManagerForTest();
  await session.ensureSession();
  let expiredCalls = 0;
  const unsub = session.onSessionExpired(() => {
    expiredCalls += 1;
  });
  session.notifyExpired();
  expect(expiredCalls).toBe(1);
  expect(session.getCurrent()).toBeNull();
  // Second notification also fires (listener not auto-removed).
  session.notifyExpired();
  expect(expiredCalls).toBe(2);
  unsub();
  session.notifyExpired();
  expect(expiredCalls).toBe(2);
});

it("attachCsrf sets X-CSRF-Token on Headers after session creation", async () => {
  httpServer.use(...defaultHandlers);
  const session = createSessionManagerForTest();
  const headers = new Headers();
  // Before session, attachCsrf is a no-op.
  session.attachCsrf(headers);
  expect(headers.get("X-CSRF-Token")).toBeNull();
  // After session, the token is attached.
  await session.ensureSession();
  session.attachCsrf(headers);
  expect(headers.get("X-CSRF-Token")).toBe("csrf_test_token");
});

it("onSessionExpired supports multiple listeners and per-listener unsubscribe", async () => {
  httpServer.use(...defaultHandlers);
  const session = createSessionManagerForTest();
  let callsA = 0;
  let callsB = 0;
  const unsubA = session.onSessionExpired(() => {
    callsA += 1;
  });
  const unsubB = session.onSessionExpired(() => {
    callsB += 1;
  });
  session.notifyExpired();
  expect(callsA).toBe(1);
  expect(callsB).toBe(1);
  unsubA();
  session.notifyExpired();
  expect(callsA).toBe(1);
  expect(callsB).toBe(2);
  unsubB();
  session.notifyExpired();
  expect(callsA).toBe(1);
  expect(callsB).toBe(2);
});

it("ensureSession throws when session creation fails", async () => {
  httpServer.use(
    http.post(`${TEST_BASE_URL}/api/v2/sessions`, () =>
      HttpResponse.json(
        problem(429, "RATE_LIMITED", "Too many session creations"),
        { status: 429 },
      ),
    ),
  );
  const session = createSessionManagerForTest();
  await expect(session.ensureSession()).rejects.toThrow();
  expect(session.getCurrent()).toBeNull();
});

it("revokeSession throws when DELETE returns a non-204, non-404 status", async () => {
  httpServer.use(
    http.delete(`${TEST_BASE_URL}/api/v2/sessions/current`, () =>
      HttpResponse.json(problem(500, "INTERNAL_ERROR", "Server error"), {
        status: 500,
      }),
    ),
  );
  const session = createSessionManager({
    baseUrl: TEST_BASE_URL,
    fetchImpl: globalThis.fetch,
  });
  // Prime the session with a working create handler.
  httpServer.use(
    http.post(`${TEST_BASE_URL}/api/v2/sessions`, () =>
      HttpResponse.json({
        data: {
          id: "sess_prime",
          expires_at: "2026-07-21T09:00:00Z",
          quota: {
            runs_per_day: 50,
            shares_per_hour: 20,
            feedbacks_per_hour: 30,
          },
          csrf_token: "csrf_prime",
        },
        meta: {},
      }),
    ),
    http.delete(`${TEST_BASE_URL}/api/v2/sessions/current`, () =>
      HttpResponse.json(problem(500, "INTERNAL_ERROR", "Server error"), {
        status: 500,
      }),
    ),
  );
  await session.ensureSession();
  await expect(session.revokeSession()).rejects.toThrow();
  // On failure the session is NOT cleared — the caller decides whether to
  // retry or force-clear via notifyExpired.
  expect(session.getCurrent()).not.toBeNull();
});
