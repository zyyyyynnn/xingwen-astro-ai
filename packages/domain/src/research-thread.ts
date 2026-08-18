import type { DomainEntityId } from "./identifiers";
import type { UtcIsoTimestamp } from "./value-types";

export type ResearchThreadEntryKind =
  | "user_message"
  | "assistant_message"
  | "assistant_reasoning"
  | "clarification_question"
  | "clarification_answer";

export type ResearchThreadActor = "user" | "assistant" | "system";

export type ResearchTurnOutcome =
  | "clarification_required"
  | "draft_ready"
  | "partial"
  | "unsupported"
  | "refused";

export type ResearchThreadPublicOutcome = ResearchTurnOutcome | "unavailable";

export interface ResearchThreadUserPayload {
  readonly answerToQuestionId: DomainEntityId | null;
}

export interface ResearchThreadAssistantPayload {
  readonly outcome: ResearchThreadPublicOutcome;
  readonly warnings: readonly string[];
  readonly draftId: DomainEntityId | null;
  readonly missingInformation: readonly string[];
  readonly reason: string | null;
  readonly errorCode: string | null;
}

export interface ResearchThreadQuestionPayload extends ResearchThreadAssistantPayload {
  readonly questionId: DomainEntityId;
  readonly options: readonly string[];
}

interface ResearchThreadEntryBase<
  Kind extends ResearchThreadEntryKind,
  Actor extends ResearchThreadActor,
  Payload,
> {
  readonly id: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly sequence: number;
  readonly kind: Kind;
  readonly actor: Actor;
  readonly publicContent: string;
  readonly structuredPayload: Payload;
  readonly modelExecutionId: DomainEntityId | null;
  readonly createdAt: UtcIsoTimestamp;
}

export type ResearchThreadEntry =
  | ResearchThreadEntryBase<"user_message", "user", ResearchThreadUserPayload>
  | ResearchThreadEntryBase<
      "clarification_answer",
      "user",
      ResearchThreadUserPayload
    >
  | ResearchThreadEntryBase<
      "assistant_reasoning",
      "assistant",
      ResearchThreadAssistantPayload
    >
  | ResearchThreadEntryBase<
      "assistant_message",
      "assistant",
      ResearchThreadAssistantPayload
    >
  | ResearchThreadEntryBase<
      "clarification_question",
      "assistant",
      ResearchThreadQuestionPayload
    >;

export interface ResearchTurn {
  readonly outcome: ResearchTurnOutcome;
  readonly entries: readonly ResearchThreadEntry[];
  readonly activeDraftId: DomainEntityId | null;
  readonly modelExecutionId: DomainEntityId;
}
