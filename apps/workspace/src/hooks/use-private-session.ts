import { useCallback, useEffect, useState } from "react";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";

export interface PrivateSessionState {
  readonly status: "loading" | "ready" | "error" | "expired";
  readonly retry: () => void;
}

/** Ensure an anonymous session only for private Workspace routes. */
export function usePrivateSession(
  runtime: WorkspaceRuntimeBoundaries,
): PrivateSessionState {
  const [status, setStatus] = useState<PrivateSessionState["status"]>(() =>
    runtime.adapterKind === "fixture" ? "ready" : "loading",
  );
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => {
    if (runtime.adapterKind === "http") setStatus("loading");
    setAttempt((current) => current + 1);
  }, [runtime.adapterKind]);

  useEffect(() => {
    if (runtime.adapterKind === "fixture") return;

    let cancelled = false;
    let expired = false;
    const unsubscribe = runtime.session.onSessionExpired(() => {
      expired = true;
      if (!cancelled) setStatus("expired");
    });
    void runtime.session.ensureSession().then(
      () => {
        if (!cancelled && !expired) setStatus("ready");
      },
      () => {
        if (!cancelled && !expired) setStatus("error");
      },
    );
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [attempt, runtime]);

  return { status, retry };
}
