import type {
  CreateResearchInputDraft,
  ResearchInputRef,
  RunCheckpoint,
} from "@xingwen/domain";
import type { RunDecisionInput } from "@xingwen/data-access/ports";
import type { ResearchRunViewModel } from "@xingwen/research-adapter";
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@xingwen/ui";
import { useMemo, useState } from "react";

type CreateInputDraft = CreateResearchInputDraft;

interface RunDecisionPanelProps {
  readonly run: ResearchRunViewModel | null;
  readonly checkpoint: RunCheckpoint | null;
  readonly checkpointLoading: boolean;
  readonly inputs: readonly ResearchInputRef[];
  readonly inputsLoading: boolean;
  readonly pending: boolean;
  readonly inputPending: boolean;
  readonly retryStepKey: string | null;
  readonly errorMessage: string | null;
  readonly onDecision: (input: RunDecisionInput) => Promise<unknown>;
  readonly onUpload: (input: CreateInputDraft) => Promise<ResearchInputRef>;
  readonly onBind: (inputId: ResearchInputRef["id"]) => Promise<unknown>;
}

function inputTypeLabel(type: string): string {
  return type === "pdf" ? "PDF" : type === "text" ? "文本" : type;
}

function fileTypeFor(file: File): "pdf" | "text" | null {
  if (
    file.type === "application/pdf" ||
    file.name.toLowerCase().endsWith(".pdf")
  ) {
    return "pdf";
  }
  if (file.type.startsWith("text/") || /\.(?:txt|text|md)$/iu.test(file.name)) {
    return "text";
  }
  return null;
}

export function RunDecisionPanel({
  run,
  checkpoint,
  checkpointLoading,
  inputs,
  inputsLoading,
  pending,
  inputPending,
  retryStepKey,
  errorMessage,
  onDecision,
  onUpload,
  onBind,
}: RunDecisionPanelProps) {
  const [selectedInputId, setSelectedInputId] = useState<string>("");
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const isWaiting = run?.status === "waiting_for_input";
  const isRepairable = run?.status === "failed" && retryStepKey !== null;
  const acceptedInputs = useMemo(
    () =>
      inputs.filter(
        (input) =>
          input.status === "accepted" &&
          (checkpoint?.requiredInputTypes.includes(
            input.type as "pdf" | "text",
          ) ??
            false),
      ),
    [checkpoint?.requiredInputTypes, inputs],
  );

  if (!isWaiting && !isRepairable) return null;

  const handleUpload = async (file: File | undefined) => {
    if (!file || !run) return;
    const type = fileTypeFor(file);
    if (type === null) {
      setUploadMessage("只接受当前检查点要求的 PDF 或纯文本文件。");
      return;
    }
    if (isWaiting && !checkpoint?.requiredInputTypes.includes(type)) {
      setUploadMessage(`当前检查点不接受 ${inputTypeLabel(type)} 输入。`);
      return;
    }
    setUploadMessage(null);
    const created =
      type === "text"
        ? await onUpload({
            type: "text",
            projectId: run.projectId,
            textContent: await file.text(),
            filename: file.name,
            mimeType: file.type || "text/plain",
          })
        : await onUpload({
            type: "pdf",
            projectId: run.projectId,
            content: await file.arrayBuffer(),
            filename: file.name,
            mimeType: file.type || "application/pdf",
          });
    setSelectedInputId(String(created.id));
  };

  const resume = async () => {
    if (!selectedInputId || pending) return;
    await onBind(selectedInputId as ResearchInputRef["id"]);
    await onDecision({
      decision: "resume",
      inputIds: [selectedInputId as ResearchInputRef["id"]],
    });
  };

  return (
    <section
      className="run-decision-panel"
      aria-label={isWaiting ? "运行输入检查点" : "运行失败处理"}
      aria-busy={pending || inputPending}
    >
      {isWaiting ? (
        <>
          <div className="run-decision-panel__heading">
            <div>
              <h2>需要你的输入</h2>
              <p>{checkpoint?.publicMessage ?? "正在读取输入检查点…"}</p>
            </div>
            <Badge variant="secondary">等待输入</Badge>
          </div>
          {checkpointLoading ? (
            <p className="text-sm text-[var(--oh-muted)]" role="status">
              正在读取检查点…
            </p>
          ) : checkpoint ? (
            <>
              <dl className="run-decision-panel__facts">
                <div>
                  <dt>步骤</dt>
                  <dd>{checkpoint.stepKey}</dd>
                </div>
                <div>
                  <dt>所需输入</dt>
                  <dd>
                    {checkpoint.requiredInputTypes
                      .map(inputTypeLabel)
                      .join(" / ")}
                  </dd>
                </div>
              </dl>
              <div className="run-decision-panel__controls">
                <label htmlFor="run-input-upload">上传当前项目输入</label>
                <Input
                  id="run-input-upload"
                  type="file"
                  accept=".pdf,.txt,.text,.md,application/pdf,text/plain"
                  disabled={pending || inputPending}
                  onChange={(event) => {
                    void handleUpload(event.currentTarget.files?.[0]).catch(
                      () => setUploadMessage("输入上传失败，请重试。"),
                    );
                  }}
                />
                <p className="text-xs text-[var(--oh-muted)]">
                  文件会先归属当前项目，再绑定到这次运行。
                </p>
              </div>
              <div className="run-decision-panel__controls">
                <label htmlFor="accepted-run-input">选择已接受输入</label>
                <Select
                  value={selectedInputId}
                  disabled={pending || inputPending || inputsLoading}
                  onValueChange={setSelectedInputId}
                >
                  <SelectTrigger
                    id="accepted-run-input"
                    className="w-full"
                    aria-describedby="accepted-run-input-help"
                  >
                    <SelectValue
                      placeholder={
                        inputsLoading ? "正在读取项目输入…" : "请选择输入"
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {acceptedInputs.map((input) => (
                      <SelectItem key={input.id} value={input.id}>
                        {input.filename ?? input.id} ·{" "}
                        {inputTypeLabel(input.type)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p
                  id="accepted-run-input-help"
                  className="text-xs text-[var(--oh-muted)]"
                >
                  仅显示当前项目中状态为“已接受”且符合检查点要求的输入。
                </p>
              </div>
              {acceptedInputs.length === 0 && !inputsLoading ? (
                <p className="text-xs text-[var(--oh-muted)]">
                  暂无可用输入，请上传一个符合要求的文件。
                </p>
              ) : null}
              <div className="run-decision-panel__actions">
                <Button
                  onClick={() => void resume()}
                  disabled={!selectedInputId || pending || inputPending}
                  aria-disabled={!selectedInputId || pending || inputPending}
                >
                  {pending || inputPending ? "正在继续…" : "继续运行"}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => void onDecision({ decision: "cancel" })}
                  disabled={pending || inputPending}
                >
                  取消运行
                </Button>
              </div>
            </>
          ) : null}
        </>
      ) : (
        <div className="run-decision-panel__heading">
          <div>
            <h2>运行失败，可尝试修复</h2>
            <p>{run?.failure?.summary ?? "失败步骤可以重新执行。"}</p>
          </div>
          <Badge variant="outline">可重试</Badge>
        </div>
      )}
      {isRepairable ? (
        <div className="run-decision-panel__actions">
          <Button
            variant="secondary"
            disabled={pending || retryStepKey === null}
            onClick={() =>
              retryStepKey
                ? void onDecision({
                    decision: "retry",
                    stepKey: retryStepKey,
                  })
                : undefined
            }
          >
            {pending ? "正在重试…" : "重试失败步骤"}
          </Button>
        </div>
      ) : null}
      {uploadMessage ? (
        <Alert variant="destructive" className="mt-3">
          <AlertDescription>{uploadMessage}</AlertDescription>
        </Alert>
      ) : null}
      {errorMessage ? (
        <Alert variant="destructive" className="mt-3">
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}
    </section>
  );
}
