import type {
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
} from "@xingwen/research-adapter";
import {
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@xingwen/ui";
import {
  ChevronDown,
  FileSearch,
  ListChecks,
  type LucideIcon,
} from "@xingwen/ui/icons";
import { ResearchPlanStatusIcon } from "./research-plan";
import type { ResearchPresentation } from "../presentation/research-presentation";

interface ResearchInspectorProps {
  readonly draft: ResearchContractDraftViewModel | null;
  readonly contract: ResearchContractViewModel | null;
  readonly presentation: ResearchPresentation;
}

interface InspectorDisclosureProps {
  readonly title: string;
  readonly status?: string;
  readonly icon: LucideIcon;
  readonly kind: "protocol" | "plan";
  readonly children: React.ReactNode;
}

function InspectorDisclosure({
  title,
  status,
  icon: Icon,
  kind,
  children,
}: InspectorDisclosureProps) {
  return (
    <Collapsible
      className="research-inspector__section"
      defaultOpen
      data-kind={kind}
    >
      <CollapsibleTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="small"
          className="research-inspector__trigger w-full justify-start"
        >
          <Icon data-icon="inline-start" aria-hidden="true" />
          <span
            className="min-w-0 flex-1 text-left"
            role="heading"
            aria-level={3}
          >
            {title}
          </span>
          {status ? (
            <span className="research-inspector__status">{status}</span>
          ) : null}
          <ChevronDown
            className="research-inspector__chevron"
            data-icon="inline-end"
            aria-hidden="true"
          />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="research-inspector__content">
        {children}
      </CollapsibleContent>
    </Collapsible>
  );
}

export function ResearchInspector({
  draft,
  contract,
  presentation,
}: ResearchInspectorProps) {
  return (
    <section className="research-inspector" aria-label="研究概览">
      <InspectorDisclosure
        title="研究协议"
        status={presentation.protocolStatus}
        icon={FileSearch}
        kind="protocol"
      >
        <p>
          {contract?.researchGoal ??
            draft?.intent ??
            "研究助手生成草案后，可在主对话中检查并确认。"}
        </p>
      </InspectorDisclosure>
      <InspectorDisclosure
        title="研究计划"
        status={presentation.statusLabel}
        icon={ListChecks}
        kind="plan"
      >
        <ol className="research-inspector__plan">
          {presentation.planItems.map((item) => (
            <li key={item.id} data-status={item.status}>
              <span className="research-inspector__plan-icon">
                <ResearchPlanStatusIcon status={item.status} />
              </span>
              <span className="min-w-0 flex-1">{item.label}</span>
            </li>
          ))}
        </ol>
      </InspectorDisclosure>
    </section>
  );
}
