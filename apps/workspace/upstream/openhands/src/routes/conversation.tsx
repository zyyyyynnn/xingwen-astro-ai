import { ConversationMain } from "../components/features/conversation/conversation-main/conversation-main";
import type { AgentWorkspaceRuntime } from "../root";

interface ConversationViewProps {
  readonly runtime: AgentWorkspaceRuntime;
}

export function ConversationView({ runtime }: ConversationViewProps) {
  return <ConversationMain runtime={runtime} />;
}

export default ConversationView;
