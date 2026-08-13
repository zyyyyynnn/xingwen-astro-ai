import { RouterProvider } from "@tanstack/react-router";
import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { createAppRouter } from "./router";
import { createWorkspaceRuntime } from "./runtime";
import "./styles.css";

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Workspace root element is missing.");
}

const runtime = createWorkspaceRuntime();
const router = createAppRouter(runtime);

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={runtime.queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
