import { createServer, type RequestListener } from "node:http";
import { expect, test } from "@playwright/test";
import { requestApi } from "./api-request";

async function withServer(
  listener: RequestListener,
  run: (url: string) => Promise<void>,
) {
  const server = createServer(listener);
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (address === null || typeof address === "string") {
    throw new Error("Test server did not bind a TCP address");
  }
  try {
    await run(`http://127.0.0.1:${address.port}/api/runs/example`);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
}

test("a read recovers from one connection reset", async ({ request }) => {
  let calls = 0;
  await withServer(
    (incoming, response) => {
      calls += 1;
      if (calls === 1) return incoming.socket.destroy();
      response.setHeader("Content-Type", "application/json");
      response.end(JSON.stringify({ data: { status: "completed" } }));
    },
    async (url) => {
      const response = await requestApi(request, url);
      expect(await response.json()).toEqual({ data: { status: "completed" } });
      expect(calls).toBe(2);
    },
  );
});

for (const method of ["GET", "POST"] as const) {
  test(`${method} failures are bounded and omit private request metadata`, async ({
    request,
  }) => {
    let calls = 0;
    await withServer(
      (incoming) => {
        calls += 1;
        incoming.socket.destroy();
      },
      async (url) => {
        const failure = await requestApi(request, url, {
          method,
          headers: {
            Cookie: "xingwen_session=test-private-session",
            "X-CSRF-Token": "test-private-csrf",
          },
        }).catch((error: unknown) => error);
        expect(failure).toBeInstanceOf(Error);
        expect(String(failure)).toContain("connection reset");
        expect(String(failure)).not.toMatch(/test-private|cookie|csrf/iu);
        expect(calls).toBe(method === "GET" ? 3 : 1);
      },
    );
  });
}

test("HTTP failures are not retried or echoed as private response bodies", async ({
  request,
}) => {
  let calls = 0;
  await withServer(
    (_incoming, response) => {
      calls += 1;
      response.statusCode = 503;
      response.end("private server diagnostics");
    },
    async (url) => {
      await expect(requestApi(request, url)).rejects.toThrow(
        "GET /api/runs/example returned HTTP 503",
      );
      expect(calls).toBe(1);
    },
  );
});
