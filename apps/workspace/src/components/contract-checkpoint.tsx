import { useMemo, useState } from "react";
import {
  ARTIFACT_KINDS,
  asEntityId,
  isArtifactKind,
  isExecutionMode,
  validateContractInputInvariants,
  type ExecutionMode,
  type ResearchContractInput,
} from "@xingwen/domain";
import type {
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
  ResearchRunViewModel,
} from "@xingwen/research-adapter";
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from "@xingwen/ui";

interface ContractCheckpointProps {
  readonly intent: string;
  readonly draft: ResearchContractDraftViewModel | null;
  readonly contract: ResearchContractViewModel | null;
  readonly run: ResearchRunViewModel | null;
  readonly pendingAction:
    "create-draft" | "save-draft" | "confirm-contract" | "create-run" | null;
  readonly errorMessage: string | null;
  readonly onCreateDraft: (
    intent: string,
    contract: ResearchContractInput,
  ) => Promise<void>;
  readonly onSaveDraft: (
    intent: string,
    contract: ResearchContractInput,
  ) => Promise<void>;
  readonly onConfirmContract: () => Promise<void>;
  readonly onCreateRun: (mode: ExecutionMode) => Promise<void>;
}

interface ContractFormState {
  intent: string;
  researchGoal: string;
  targetObjects: string;
  requestedFields: string;
  allowedSources: string;
  keywords: string;
  yearFrom: string;
  yearTo: string;
  sourceIds: string;
  maxCandidates: string;
  outputRequirements: string;
  requireLocator: "true" | "false";
  requireSourceSnapshot: "true" | "false";
  minimumCoverage: string;
  sourceCompletenessMin: string;
  unitConsistencyMin: string;
}

const AUTHORITY_DEFAULTS: Omit<ContractFormState, "intent"> = {
  researchGoal: "",
  targetObjects: "",
  requestedFields: "",
  allowedSources: "",
  keywords: "",
  yearFrom: "",
  yearTo: "",
  sourceIds: "",
  maxCandidates: "20",
  outputRequirements: "",
  requireLocator: "true",
  requireSourceSnapshot: "true",
  minimumCoverage: "1",
  sourceCompletenessMin: "1",
  unitConsistencyMin: "1",
};

function list(value: string): string[] {
  return value
    .split(/[,，\n]/u)
    .map((item) => item.trim())
    .filter(Boolean);
}

function booleanSelectValue(value: string): "true" | "false" {
  return value === "false" ? "false" : "true";
}

function formFromDraft(
  intent: string,
  draft: ResearchContractDraftViewModel | null,
): ContractFormState {
  if (!draft) return { intent, ...AUTHORITY_DEFAULTS };
  return {
    intent: draft.intent,
    researchGoal: draft.contract.researchGoal,
    targetObjects: draft.contract.targetObjects.join(", "),
    requestedFields: draft.contract.requestedFields.join(", "),
    allowedSources: draft.contract.sourceScope.allowedSources.join(", "),
    keywords: draft.contract.paperSearchScope.keywords.join(", "),
    yearFrom: draft.contract.paperSearchScope.yearFrom?.toString() ?? "",
    yearTo: draft.contract.paperSearchScope.yearTo?.toString() ?? "",
    sourceIds: draft.contract.paperSearchScope.sourceIds.join(", "),
    maxCandidates: draft.contract.paperSearchScope.maxCandidates.toString(),
    outputRequirements: draft.contract.outputRequirements.join(", "),
    requireLocator: draft.contract.evidenceRequirements.requireLocator
      ? "true"
      : "false",
    requireSourceSnapshot: draft.contract.evidenceRequirements
      .requireSourceSnapshot
      ? "true"
      : "false",
    minimumCoverage:
      draft.contract.evidenceRequirements.minimumCoverage.toString(),
    sourceCompletenessMin:
      draft.contract.qualityConstraints.sourceCompletenessMin.toString(),
    unitConsistencyMin:
      draft.contract.qualityConstraints.unitConsistencyMin.toString(),
  };
}

function parseOptionalYear(value: string): number | null {
  return value.trim() ? Number(value) : null;
}

function parseContract(form: ContractFormState): {
  readonly input: ResearchContractInput | null;
  readonly errors: string[];
} {
  const errors: string[] = [];
  const targetObjects = list(form.targetObjects).map(asEntityId);
  const requestedFields = list(form.requestedFields).map(asEntityId);
  const allowedSources = list(form.allowedSources).map(asEntityId);
  const outputRequirements = list(form.outputRequirements);
  const maxCandidates = Number(form.maxCandidates);
  const minimumCoverage = Number(form.minimumCoverage);
  const sourceCompletenessMin = Number(form.sourceCompletenessMin);
  const unitConsistencyMin = Number(form.unitConsistencyMin);
  const yearFrom = parseOptionalYear(form.yearFrom);
  const yearTo = parseOptionalYear(form.yearTo);

  if (form.researchGoal.trim().length < 4)
    errors.push("研究目标至少需要 4 个字符。");
  if (targetObjects.length === 0) errors.push("请明确至少一个目标对象。");
  if (requestedFields.length === 0) errors.push("请明确至少一个请求字段。");
  if (allowedSources.length === 0)
    errors.push("请明确至少一个允许的数据来源。");
  if (
    outputRequirements.length === 0 ||
    !outputRequirements.every(isArtifactKind)
  ) {
    errors.push(`输出类型必须取自：${ARTIFACT_KINDS.join("、")}。`);
  }
  if (
    !Number.isInteger(maxCandidates) ||
    maxCandidates < 1 ||
    maxCandidates > 100
  ) {
    errors.push("文献候选数量必须是 1–100 的整数。");
  }
  if (
    [minimumCoverage, sourceCompletenessMin, unitConsistencyMin].some(
      (value) => !Number.isFinite(value) || value < 0 || value > 1,
    )
  ) {
    errors.push("证据覆盖率与质量阈值必须在 0–1 之间。");
  }
  if (
    [yearFrom, yearTo].some(
      (value) =>
        value !== null &&
        (!Number.isInteger(value) || value < 1900 || value > 9999),
    )
  ) {
    errors.push("文献年份必须是 1900–9999 的整数。");
  }

  if (errors.length > 0) return { input: null, errors };
  const input: ResearchContractInput = {
    researchGoal: form.researchGoal.trim(),
    targetObjects,
    dataRequirements: { unitPolicy: "canonical" },
    requestedFields,
    sourceScope: { allowedSources },
    paperSearchScope: {
      keywords: list(form.keywords),
      yearFrom,
      yearTo,
      sourceIds: list(form.sourceIds).map(asEntityId),
      maxCandidates,
    },
    outputRequirements: outputRequirements.filter(isArtifactKind),
    evidenceRequirements: {
      requireLocator: form.requireLocator === "true",
      requireSourceSnapshot: form.requireSourceSnapshot === "true",
      minimumCoverage,
    },
    qualityConstraints: { sourceCompletenessMin, unitConsistencyMin },
  };
  errors.push(...validateContractInputInvariants(input));
  return { input: errors.length === 0 ? input : null, errors };
}

export function ContractCheckpoint({ ...props }: ContractCheckpointProps) {
  const formKey = props.draft
    ? `${String(props.draft.id)}:${String(props.draft.version)}`
    : `intent:${props.intent}`;

  return <ContractCheckpointForm key={formKey} {...props} />;
}

function ContractCheckpointForm({
  intent,
  draft,
  contract,
  run,
  pendingAction,
  errorMessage,
  onCreateDraft,
  onSaveDraft,
  onConfirmContract,
  onCreateRun,
}: ContractCheckpointProps) {
  const [form, setForm] = useState(() => formFromDraft(intent, draft));
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [executionMode, setExecutionMode] = useState<"" | ExecutionMode>("");

  const baseline = useMemo(
    () => JSON.stringify(formFromDraft(intent, draft)),
    [draft, intent],
  );
  const dirty = draft !== null && JSON.stringify(form) !== baseline;
  const pending = pendingAction !== null;

  const update = <K extends keyof ContractFormState>(
    key: K,
    value: ContractFormState[K],
  ) => setForm((current) => ({ ...current, [key]: value }));

  const submitDraft = async (kind: "create" | "save") => {
    const parsed = parseContract(form);
    setValidationErrors(parsed.errors);
    if (!parsed.input || !form.intent.trim()) return;
    if (kind === "create") {
      await onCreateDraft(form.intent.trim(), parsed.input);
    } else {
      await onSaveDraft(form.intent.trim(), parsed.input);
    }
  };

  if (run) {
    return (
      <section
        className="contract-checkpoint"
        aria-labelledby="run-context-title"
      >
        <div className="checkpoint-heading">
          <div>
            <h2 id="run-context-title">当前研究运行</h2>
            <p>Run 快照是当前状态的权威来源；公开活动按事件序列恢复。</p>
          </div>
          <Badge variant={run.isFailed ? "destructive" : "secondary"}>
            {run.status}
          </Badge>
        </div>
        <dl className="checkpoint-summary">
          <div>
            <dt>执行模式</dt>
            <dd>{run.executionMode}</dd>
          </div>
          <div>
            <dt>进度</dt>
            <dd>{run.progress}%</dd>
          </div>
          <div>
            <dt>最新事件序列</dt>
            <dd>{run.latestEventSequence}</dd>
          </div>
        </dl>
        {run.failure ? (
          <Alert variant="destructive">
            <AlertTitle>研究运行失败</AlertTitle>
            <AlertDescription>
              {run.failure.summary ?? "服务未提供公开失败摘要。"}
            </AlertDescription>
          </Alert>
        ) : null}
      </section>
    );
  }

  if (contract) {
    return (
      <section
        className="contract-checkpoint"
        aria-labelledby="run-create-title"
      >
        <div className="checkpoint-heading">
          <div>
            <h2 id="run-create-title">研究协议已确认</h2>
            <p>协议已冻结。明确选择执行模式后创建真实 Research Run。</p>
          </div>
          <Badge>已确认</Badge>
        </div>
        <Field>
          <FieldLabel htmlFor="execution-mode">执行模式</FieldLabel>
          <Select
            value={executionMode}
            disabled={pending}
            onValueChange={(value) => {
              setExecutionMode(isExecutionMode(value) ? value : "");
            }}
          >
            <SelectTrigger id="execution-mode">
              <SelectValue placeholder="请选择" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="live">Live</SelectItem>
              <SelectItem value="demo_replay">Demo Replay</SelectItem>
            </SelectContent>
          </Select>
          <FieldDescription>
            界面只展示服务端返回的真实执行模式与状态。
          </FieldDescription>
        </Field>
        {errorMessage ? (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        ) : null}
        <Button
          disabled={pending || executionMode === ""}
          onClick={() => {
            if (executionMode) void onCreateRun(executionMode);
          }}
        >
          {pendingAction === "create-run" ? "正在创建运行…" : "创建研究运行"}
        </Button>
      </section>
    );
  }

  return (
    <section
      className="contract-checkpoint"
      aria-labelledby="contract-checkpoint-title"
    >
      <div className="checkpoint-heading">
        <div>
          <h2 id="contract-checkpoint-title">研究协议检查点</h2>
          <p>研究意图不会自动扩写为协议。请明确所有研究边界后保存并确认。</p>
        </div>
        <Badge variant="outline">
          {draft ? `草稿 v${String(draft.version)}` : "尚未创建草稿"}
        </Badge>
      </div>
      <FieldGroup>
        <Field data-invalid={!form.intent.trim()}>
          <FieldLabel htmlFor="contract-intent">研究意图</FieldLabel>
          <Textarea
            id="contract-intent"
            value={form.intent}
            disabled={pending}
            onChange={(event) => update("intent", event.currentTarget.value)}
          />
        </Field>
        <Field
          data-invalid={
            form.researchGoal.trim().length > 0 &&
            form.researchGoal.trim().length < 4
          }
        >
          <FieldLabel htmlFor="research-goal">研究目标</FieldLabel>
          <Textarea
            id="research-goal"
            value={form.researchGoal}
            disabled={pending}
            maxLength={500}
            placeholder="明确可验证的科研目标（4–500 字符）"
            onChange={(event) =>
              update("researchGoal", event.currentTarget.value)
            }
          />
        </Field>
        <div className="checkpoint-field-grid">
          <Field>
            <FieldLabel htmlFor="target-objects">目标对象</FieldLabel>
            <Input
              id="target-objects"
              value={form.targetObjects}
              disabled={pending}
              placeholder="逗号分隔"
              onChange={(event) =>
                update("targetObjects", event.currentTarget.value)
              }
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="requested-fields">请求字段</FieldLabel>
            <Input
              id="requested-fields"
              value={form.requestedFields}
              disabled={pending}
              placeholder="逗号分隔"
              onChange={(event) =>
                update("requestedFields", event.currentTarget.value)
              }
            />
          </Field>
        </div>
        <Field>
          <FieldLabel htmlFor="allowed-sources">允许来源</FieldLabel>
          <Input
            id="allowed-sources"
            value={form.allowedSources}
            disabled={pending}
            placeholder="明确来源标识，逗号分隔"
            onChange={(event) =>
              update("allowedSources", event.currentTarget.value)
            }
          />
        </Field>
        <FieldSet>
          <FieldLegend>文献检索范围</FieldLegend>
          <div className="checkpoint-field-grid">
            <Field>
              <FieldLabel htmlFor="keywords">关键词</FieldLabel>
              <Input
                id="keywords"
                value={form.keywords}
                disabled={pending}
                placeholder="可选，逗号分隔"
                onChange={(event) =>
                  update("keywords", event.currentTarget.value)
                }
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="source-ids">来源 ID</FieldLabel>
              <Input
                id="source-ids"
                value={form.sourceIds}
                disabled={pending}
                placeholder="可选，逗号分隔"
                onChange={(event) =>
                  update("sourceIds", event.currentTarget.value)
                }
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="year-from">起始年份</FieldLabel>
              <Input
                id="year-from"
                type="number"
                min={1900}
                max={9999}
                value={form.yearFrom}
                disabled={pending}
                onChange={(event) =>
                  update("yearFrom", event.currentTarget.value)
                }
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="year-to">结束年份</FieldLabel>
              <Input
                id="year-to"
                type="number"
                min={1900}
                max={9999}
                value={form.yearTo}
                disabled={pending}
                onChange={(event) =>
                  update("yearTo", event.currentTarget.value)
                }
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="max-candidates">候选数量</FieldLabel>
              <Input
                id="max-candidates"
                type="number"
                min={1}
                max={100}
                value={form.maxCandidates}
                disabled={pending}
                onChange={(event) =>
                  update("maxCandidates", event.currentTarget.value)
                }
              />
            </Field>
          </div>
        </FieldSet>
        <Field>
          <FieldLabel htmlFor="output-requirements">输出类型</FieldLabel>
          <Input
            id="output-requirements"
            value={form.outputRequirements}
            disabled={pending}
            placeholder="例如：dataset, paper_collection"
            onChange={(event) =>
              update("outputRequirements", event.currentTarget.value)
            }
          />
          <FieldDescription>{ARTIFACT_KINDS.join("、")}</FieldDescription>
        </Field>
        <FieldSet>
          <FieldLegend>证据与质量约束</FieldLegend>
          <div className="checkpoint-field-grid">
            <Field>
              <FieldLabel htmlFor="require-locator">要求定位信息</FieldLabel>
              <Select
                value={form.requireLocator}
                disabled={pending}
                onValueChange={(value) =>
                  update("requireLocator", booleanSelectValue(value))
                }
              >
                <SelectTrigger id="require-locator">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="true">是</SelectItem>
                  <SelectItem value="false">否</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="require-snapshot">要求来源快照</FieldLabel>
              <Select
                value={form.requireSourceSnapshot}
                disabled={pending}
                onValueChange={(value) =>
                  update("requireSourceSnapshot", booleanSelectValue(value))
                }
              >
                <SelectTrigger id="require-snapshot">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="true">是</SelectItem>
                  <SelectItem value="false">否</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field>
              <FieldLabel htmlFor="minimum-coverage">最低证据覆盖率</FieldLabel>
              <Input
                id="minimum-coverage"
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={form.minimumCoverage}
                disabled={pending}
                onChange={(event) =>
                  update("minimumCoverage", event.currentTarget.value)
                }
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="source-completeness">
                来源完整性阈值
              </FieldLabel>
              <Input
                id="source-completeness"
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={form.sourceCompletenessMin}
                disabled={pending}
                onChange={(event) =>
                  update("sourceCompletenessMin", event.currentTarget.value)
                }
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="unit-consistency">单位一致性阈值</FieldLabel>
              <Input
                id="unit-consistency"
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={form.unitConsistencyMin}
                disabled={pending}
                onChange={(event) =>
                  update("unitConsistencyMin", event.currentTarget.value)
                }
              />
            </Field>
            <Field data-disabled>
              <FieldLabel htmlFor="unit-policy">单位策略</FieldLabel>
              <Input id="unit-policy" value="canonical" disabled />
              <FieldDescription>当前 Authority 唯一允许值。</FieldDescription>
            </Field>
          </div>
        </FieldSet>
      </FieldGroup>
      {validationErrors.length > 0 ? (
        <FieldError errors={validationErrors.map((message) => ({ message }))} />
      ) : null}
      {errorMessage ? (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}
      <div className="checkpoint-actions">
        {draft ? (
          <>
            <Button
              variant="secondary"
              disabled={pending || !dirty}
              onClick={() => void submitDraft("save")}
            >
              {pendingAction === "save-draft" ? "正在保存…" : "保存草稿"}
            </Button>
            <Button
              disabled={pending || dirty}
              onClick={() => void onConfirmContract()}
            >
              {pendingAction === "confirm-contract"
                ? "正在确认…"
                : "确认研究协议"}
            </Button>
          </>
        ) : (
          <Button
            disabled={pending || !form.intent.trim()}
            onClick={() => void submitDraft("create")}
          >
            {pendingAction === "create-draft"
              ? "正在创建草稿…"
              : "创建协议草稿"}
          </Button>
        )}
      </div>
    </section>
  );
}
