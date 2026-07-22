import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import {
  createFixtureRepositories,
  exoplanetHostStarFixture,
} from "@xingwen/data-access";
import {
  createGuidedTourController,
  createWorkspaceController,
} from "@xingwen/workspace-core";

import type { WorkspaceRuntimeBoundaries } from "./boundaries";
import { createAppRouter } from "./router";
import "./styles.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Workspace root element is missing.");
}

const repositories = createFixtureRepositories(exoplanetHostStarFixture);
const tour = createGuidedTourController();
const workspaceController = createWorkspaceController(repositories);

const boundaries: WorkspaceRuntimeBoundaries = {
  repositories,
  tour,
  workspaceController,
};

const router = createAppRouter(boundaries);

createRoot(rootElement).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
