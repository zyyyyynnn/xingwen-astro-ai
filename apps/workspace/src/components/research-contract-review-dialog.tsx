import type {
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
} from "@xingwen/research-adapter";
import type { ResearchPlanningCatalog } from "@xingwen/domain";
import { useRef, useState } from "react";
import {
  Alert,
  AlertDescription,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertTitle,
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  ScrollArea,
  Separator,
} from "@xingwen/ui";
import {
  Check,
  ChevronDown,
  Database,
  ListChecks,
  PackageCheck,
  ShieldCheck,
  Target,
  type LucideIcon,
} from "@xingwen/ui/icons";

import { ResearchContractForm } from "./research-contract-form";
import { optionLabel } from "./research-contract-options";

interface ResearchContractReviewDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly draft: ResearchContractDraftViewModel | null;
  readonly catalog: ResearchPlanningCatalog | null;
  readonly contract: ResearchContractViewModel | null;
  readonly runStatusLabel: string | null;
  readonly pendingAction:
    "save-draft" | "confirm-contract" | "create-run" | null;
  readonly errorMessage: string | null;
  readonly onSave: (
    intent: string,
    contract: ResearchContractDraftViewModel["contract"],
  ) => Promise<void>;
  readonly onConfirmAndRun: () => Promise<void>;
  readonly onViewPlan?: () => void;
}

function FactLabel({
  icon: Icon,
  children,
}: {
  readonly icon: LucideIcon;
  readonly children: string;
}) {
  return (
    <span className="research-contract-facts__label">
      <Icon aria-hidden="true" />
      {children}
    </span>
  );
}

function ContractFacts({
  contract,
  catalog,
}: {
  readonly contract: ResearchContractDraftViewModel["contract"];
  readonly catalog: ResearchPlanningCatalog;
}) {
  const targetObjects = contract.targetObjects
    .map((value) => optionLabel(catalog.targetObjects, value))
    .join("、");
  const allowedSources = contract.sourceScope.allowedSources
    .map((value) => optionLabel(catalog.allowedSources, value))
    .join("、");
  const requestedFields = contract.requestedFields.map((value) =>
    optionLabel(catalog.requestedFields, value),
  );
  const outputRequirements = contract.outputRequirements
    .map((value) => optionLabel(catalog.outputRequirements, value))
    .join("、");
  const minimumCoverage = Math.round(
    contract.evidenceRequirements.minimumCoverage * 100,
  );

  return (
    <div className="research-contract-facts">
      <section className="research-contract-facts__section research-contract-facts__goal">
        <FactLabel icon={Target}>研究目标</FactLabel>
        <p>{contract.researchGoal}</p>
      </section>

      <Separator />

      <div className="research-contract-facts__pair">
        <section className="research-contract-facts__section">
          <FactLabel icon={ListChecks}>目标对象</FactLabel>
          <p>{targetObjects}</p>
        </section>
        <section className="research-contract-facts__section">
          <FactLabel icon={ShieldCheck}>允许来源</FactLabel>
          <p>{allowedSources}</p>
        </section>
      </div>

      <Separator />

      <Collapsible className="research-contract-facts__data">
        <CollapsibleTrigger asChild>
          <Button
            variant="ghost"
            className="research-contract-facts__data-trigger"
          >
            <FactLabel icon={Database}>研究数据</FactLabel>
            <span className="research-contract-facts__data-meta">
              {requestedFields.length} 项
              <ChevronDown aria-hidden="true" />
            </span>
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <ul className="research-contract-facts__data-list">
            {requestedFields.map((field) => (
              <li key={field}>
                <Check aria-hidden="true" />
                <span>{field}</span>
              </li>
            ))}
          </ul>
        </CollapsibleContent>
      </Collapsible>

      <Separator />

      <div className="research-contract-facts__pair research-contract-facts__closing">
        <section className="research-contract-facts__section">
          <FactLabel icon={PackageCheck}>目标成果</FactLabel>
          <p>{outputRequirements}</p>
        </section>
        <section className="research-contract-facts__section">
          <FactLabel icon={ShieldCheck}>证据覆盖率</FactLabel>
          <p className="research-contract-facts__coverage">
            ≥ {minimumCoverage}%
          </p>
        </section>
      </div>
    </div>
  );
}

export function ResearchContractReviewDialog({
  open,
  onOpenChange,
  draft,
  catalog,
  contract,
  runStatusLabel,
  pendingAction,
  errorMessage,
  onSave,
  onConfirmAndRun,
}: ResearchContractReviewDialogProps) {
  const [dirty, setDirty] = useState(false);
  const [discardPromptOpen, setDiscardPromptOpen] = useState(false);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const review = draft?.contract ?? contract;
  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && dirty) {
      setDiscardPromptOpen(true);
      return;
    }
    setDiscardPromptOpen(false);
    onOpenChange(nextOpen);
  };
  return (
    <>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent
          className={`research-contract-dialog ${draft ? "research-contract-dialog--editor" : "research-contract-dialog--confirmed"}`}
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            titleRef.current?.focus();
          }}
        >
          <DialogHeader className="research-contract-dialog__header">
            <div className="research-contract-dialog__intro">
              <DialogTitle
                ref={titleRef}
                tabIndex={-1}
                className="flex items-center gap-2"
              >
                <span>{contract ? "研究协议" : "研究协议草案"}</span>
                {contract ? (
                  <span className="text-sm font-normal text-[var(--oh-status-success)]">
                    已确认
                  </span>
                ) : null}
              </DialogTitle>
              <DialogDescription>
                {draft
                  ? "逐项核对研究边界、来源和目标产物；保存后才能确认。"
                  : runStatusLabel
                    ? "研究边界已锁定；当前研究将持续遵循这份协议。"
                    : "研究边界已锁定；确认无误后即可开始研究。"}
              </DialogDescription>
            </div>
          </DialogHeader>

          {draft && catalog ? (
            <div className="research-contract-dialog__body">
              <ResearchContractForm
                draft={draft}
                catalog={catalog}
                pendingAction={
                  pendingAction === "save-draft" ||
                  pendingAction === "confirm-contract"
                    ? pendingAction
                    : null
                }
                errorMessage={errorMessage}
                onSaveDraft={onSave}
                onConfirmAndRun={onConfirmAndRun}
                onDirtyChange={setDirty}
              />

              {draft.warnings.length ? (
                <Alert className="research-contract-dialog__notice">
                  <AlertTitle>需要留意</AlertTitle>
                  <AlertDescription>
                    {draft.warnings.join("；")}
                  </AlertDescription>
                </Alert>
              ) : null}
            </div>
          ) : review && catalog ? (
            <ScrollArea className="research-contract-dialog__scroller">
              <div className="research-contract-dialog__body--confirmed">
                <ContractFacts contract={review} catalog={catalog} />

                {errorMessage ? (
                  <Alert variant="destructive">
                    <AlertDescription>{errorMessage}</AlertDescription>
                  </Alert>
                ) : null}
              </div>
            </ScrollArea>
          ) : null}
        </DialogContent>
      </Dialog>
      <AlertDialog open={discardPromptOpen} onOpenChange={setDiscardPromptOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>放弃未保存的修改？</AlertDialogTitle>
            <AlertDialogDescription>
              当前研究协议草案的修改尚未保存。放弃后无法恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>继续编辑</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                setDirty(false);
                setDiscardPromptOpen(false);
                onOpenChange(false);
              }}
            >
              放弃修改
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
