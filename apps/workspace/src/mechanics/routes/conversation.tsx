import { ConversationMain } from "../components/features/conversation/conversation-main/conversation-main";
import type { ResearchWorkspaceRuntime } from "../root";

interface ConversationViewProps {
  readonly runtime: ResearchWorkspaceRuntime;
}

export function ConversationView({ runtime }: ConversationViewProps) {
  return <ConversationMain runtime={runtime} />;
}

export default ConversationView;
