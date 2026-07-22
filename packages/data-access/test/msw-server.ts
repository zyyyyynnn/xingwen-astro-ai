/**
 * MSW server singleton for HTTP adapter tests.
 *
 * Started once in test setup; handlers are reset between tests. Tests install
 * custom handlers via `httpServer.use(...)` to mock specific endpoints.
 */

import { setupServer } from "msw/node";

export const httpServer = setupServer();

export async function startHttpServer(): Promise<void> {
  await httpServer.listen({ onUnhandledRequest: "error" });
}

export async function stopHttpServer(): Promise<void> {
  await httpServer.close();
}
