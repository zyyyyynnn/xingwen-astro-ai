import { QueryClient } from "@tanstack/react-query";

/**
 * Create the workspace QueryClient with sensible defaults for server state.
 *
 * - staleTime 30s: research data doesn't change every second; short enough
 *   for live runs, long enough to avoid refetch storms on navigation.
 * - refetchOnWindowFocus false: the workspace is a long-running session;
 *   focus refetches are disruptive and the controller handles freshness.
 */
export function createWorkspaceQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: 1,
      },
      mutations: {
        retry: 0,
      },
    },
  });
}
