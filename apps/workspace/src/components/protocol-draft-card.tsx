import type {
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
} from "@xingwen/research-adapter";
import {
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@xingwen/ui";
import { Play, Settings2 } from "@xingwen/ui/icons";

export interface ProtocolDraftCardProps {
  readonly draft: ResearchContractDraftViewModel | null;
  readonly contract: ResearchContractViewModel | null;
  readonly isConfirmed: boolean;
  readonly runStatusLabel: string | null;
  readonly onConfirm?: () => Promise<void> | void;
  readonly onOpenEditor?: () => void;
  readonly onRefineInChat?: () => void;
  readonly onViewPlan?: () => void;
  readonly isConfirming?: boolean;
}

export function ProtocolDraftCard({
  draft,
  contract,
  isConfirmed,
  onConfirm,
  onOpenEditor,
  onRefineInChat,
  onViewPlan,
  isConfirming = false,
}: ProtocolDraftCardProps) {
  const active = draft?.contract ?? contract;
  if (!active) return null;

  return (
    <Card
      size="small"
      className="my-3 border-[var(--color-border)] bg-[var(--color-surface)] shadow-none"
      aria-label="研究协议"
      data-testid="protocol-summary-card"
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-sm font-semibold leading-5 text-[var(--color-ink-primary)]">
            研究协议
          </CardTitle>
          <span
            className={
              isConfirmed
                ? "text-xs font-medium text-[var(--color-success)]"
                : "text-xs text-[var(--color-ink-secondary)]"
            }
          >
            {isConfirmed ? "已确认" : "待确认"}
          </span>
        </div>
      </CardHeader>

      <CardContent className="pt-1">
        <p className="ui-text-body font-serif text-[var(--color-ink-primary)]">
          {active.researchGoal}
        </p>
      </CardContent>

      <CardFooter className="flex flex-wrap items-center justify-between gap-2 pt-2">
        {!isConfirmed ? (
          <>
            <div className="flex items-center gap-2">
              <Button
                variant="primary"
                size="small"
                disabled={isConfirming}
                onClick={onConfirm}
                className="gap-1 font-medium"
              >
                <Play aria-hidden="true" />
                {isConfirming ? "正在确认并启动…" : "确认协议并开始研究"}
              </Button>
              {onOpenEditor ? (
                <Button
                  variant="secondary"
                  size="small"
                  onClick={onOpenEditor}
                  className="gap-1"
                >
                  <Settings2 aria-hidden="true" />
                  调整
                </Button>
              ) : null}
            </div>
            {onRefineInChat ? (
              <Button
                variant="ghost"
                size="small"
                onClick={onRefineInChat}
                className="text-xs text-[var(--color-ink-secondary)]"
              >
                在对话中说明修改
              </Button>
            ) : null}
          </>
        ) : (
          <div className="flex w-full justify-end gap-2">
            {onOpenEditor ? (
              <Button variant="ghost" size="small" onClick={onOpenEditor}>
                查看研究协议
              </Button>
            ) : null}
            {onViewPlan ? (
              <Button variant="secondary" size="small" onClick={onViewPlan}>
                查看执行计划
              </Button>
            ) : null}
          </div>
        )}
      </CardFooter>
    </Card>
  );
}
