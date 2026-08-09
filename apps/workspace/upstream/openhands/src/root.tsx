import MainApp from "./routes/root-layout";
import type { PublicActivityEvent } from "./components/conversation-events/chat/group-events";

export interface AgentWorkspaceRuntime {
  readonly availability: "ready" | "unavailable";
  readonly execute: (command: string, signal: AbortSignal) => Promise<void>;
  readonly activityEvents?: readonly PublicActivityEvent[];
}

export const unavailableAgentWorkspaceRuntime: AgentWorkspaceRuntime = {
  availability: "unavailable",
  execute: () => Promise.reject(new Error("Agent 运行服务未连接")),
};

interface OpenHandsWorkspaceRootProps {
  readonly runtime?: AgentWorkspaceRuntime;
}

/**
 * Source-adopted OpenHands application root. Xingwen owns only the host route
 * and injects a thin execution boundary; the product shell stays here.
 */
export function OpenHandsWorkspaceRoot({
  runtime = unavailableAgentWorkspaceRuntime,
}: OpenHandsWorkspaceRootProps) {
  return <MainApp runtime={runtime} />;
}

export default OpenHandsWorkspaceRoot;
