import { afterAll, afterEach, beforeAll } from "vitest";

import { httpServer, startHttpServer, stopHttpServer } from "./msw-server";

beforeAll(async () => {
  await startHttpServer();
});

afterEach(async () => {
  await httpServer.resetHandlers();
});

afterAll(async () => {
  await stopHttpServer();
});
