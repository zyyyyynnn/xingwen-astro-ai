import type { Page } from "@playwright/test";

const API_ORIGIN = "http://localhost:8000";
export const VISUAL_PROJECT_ID = "proj_workspace_visual_e2e";
export const VISUAL_PROJECT_NAME = "视觉回归研究";
export const WORKSPACE_PROJECT_URL = `http://127.0.0.1:15173/workspace/${VISUAL_PROJECT_ID}`;

const VISUAL_PROJECT = {
  id: VISUAL_PROJECT_ID,
  session_id: "sess_workspace_visual_e2e",
  name: VISUAL_PROJECT_NAME,
  description: "HTTP-bound shell and responsive verification",
  case_key: "exoplanet_host_star",
  active_contract_id: null,
  latest_run_id: null,
  created_at: "2026-08-11T00:00:00Z",
  updated_at: "2026-08-11T00:00:00Z",
  revision: 1,
};

function metadata() {
  return {
    request_id: "req_workspace_visual_e2e",
    schema_version: "2.0.0",
    generated_at: "2026-08-11T00:00:00Z",
  };
}

/**
 * Keep shell/visual E2E on the production HTTP boundary without requiring a
 * database. The real persistence chain is covered separately by
 * tests/e2e-integration/real-http.spec.ts.
 */
export async function installWorkspaceHttpFixture(page: Page) {
  await page.route(`${API_ORIGIN}/api/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (request.method() === "POST" && url.pathname === "/api/sessions") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: {
            status: "active",
            created_at: "2026-08-11T00:00:00Z",
            expires_at: "2026-08-12T00:00:00Z",
            quota: { max_projects: 10, max_runs: 50 },
            csrf_token: "csrf_workspace_visual_e2e",
          },
          meta: metadata(),
          links: { self: "/api/sessions/current" },
        }),
      });
      return;
    }

    if (request.method() === "GET" && url.pathname === "/api/projects") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: [VISUAL_PROJECT],
          page: { next_cursor: null, has_more: false, limit: 20 },
          meta: metadata(),
          links: { self: "/api/projects" },
        }),
      });
      return;
    }

    if (
      request.method() === "GET" &&
      url.pathname === `/api/projects/${VISUAL_PROJECT_ID}`
    ) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: VISUAL_PROJECT,
          meta: metadata(),
          links: { self: `/api/projects/${VISUAL_PROJECT_ID}` },
        }),
      });
      return;
    }

    if (
      request.method() === "DELETE" &&
      url.pathname === "/api/sessions/current"
    ) {
      await route.fulfill({ status: 204, body: "" });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/problem+json",
      body: JSON.stringify({
        type: "about:blank",
        title: "Resource not found",
        status: 404,
        detail: "The visual fixture does not define this resource.",
        code: "RESOURCE_NOT_FOUND",
      }),
    });
  });
}
