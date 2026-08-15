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
  Telescope,
  type LucideIcon,
} from "@xingwen/ui/icons";
import { ResearchPlanStatusIcon } from "./research-plan";
import type { ResearchPresentation } from "../presentation/research-presentation";

interface ResearchInspectorProps {
  readonly draft: ResearchContractDraftViewModel | null;
  readonly contract: ResearchContractViewModel | null;
  readonly presentation: ResearchPresentation;
  readonly artifactPanel: React.ReactNode;
  readonly artifactStatus: string;
  readonly runInteractionPanel: React.ReactNode;
  readonly researchInputPanel: React.ReactNode;
  readonly researchInputStatus: string;
}

interface InspectorDisclosureProps {
  readonly title: string;
  readonly status?: string;
  readonly icon: LucideIcon;
  readonly kind: "protocol" | "plan" | "run" | "inputs" | "artifacts";
  readonly defaultOpen?: boolean;
  readonly children: React.ReactNode;
}

function InspectorDisclosure({
  title,
  status,
  icon: Icon,
  kind,
  children,
  defaultOpen = true,
}: InspectorDisclosureProps) {
  return (
    <Collapsible
      className="research-inspector__section"
      defaultOpen={defaultOpen}
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
  artifactPanel,
  artifactStatus,
  runInteractionPanel,
  researchInputPanel,
  researchInputStatus,
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
      {runInteractionPanel ? (
        <InspectorDisclosure title="运行处理" icon={ListChecks} kind="run">
          {runInteractionPanel}
        </InspectorDisclosure>
      ) : null}
      <InspectorDisclosure
        title="研究输入"
        status={researchInputStatus}
        icon={FileSearch}
        kind="inputs"
        defaultOpen={false}
      >
        {researchInputPanel}
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
      <InspectorDisclosure
        title="科学制品"
        status={artifactStatus}
        icon={Telescope}
        kind="artifacts"
      >
        {artifactPanel}
      </InspectorDisclosure>
    </section>
  );
}
