import type { APIRequestContext } from "@playwright/test";

export async function requestApi(
  request: APIRequestContext,
  url: string,
  options: Parameters<APIRequestContext["fetch"]>[1] = {},
) {
  const method = (options.method ?? "GET").toUpperCase();
  const pathname = new URL(url).pathname;
  const response = await request
    .fetch(url, { ...options, maxRetries: method === "GET" ? 2 : 0 })
    .catch((error: unknown) => {
      const message = error instanceof Error ? error.message : "";
      const reason = /ECONNRESET|socket hang up/iu.test(message)
        ? "connection reset"
        : /timeout|timed out/iu.test(message)
          ? "request timed out"
          : "transport failure";
      // Playwright's raw network error includes cookies and authorization headers.
      throw new Error(`${method} ${pathname}: ${reason}`);
    });
  if (!response.ok()) {
    throw new Error(`${method} ${pathname} returned HTTP ${response.status()}`);
  }
  return response;
}
