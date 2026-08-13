import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import {
  parseEntityId,
  validateContractInputInvariants,
  type ArtifactKind,
  type ResearchContractInput,
  type ScientificTaskInput,
} from "@xingwen/domain";
import type { ResearchContractDraftViewModel } from "@xingwen/research-adapter";
import type { ResearchPlanningCatalog } from "@xingwen/domain";
import {
  Alert,
  AlertDescription,
  Button,
  Checkbox,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
  Input,
  Popover,
  PopoverContent,
  PopoverTrigger,
  ScrollArea,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
} from "@xingwen/ui";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Database,
  PackageCheck,
  Plus,
  ScanSearch,
  ShieldCheck,
  Target,
  X,
  type LucideIcon,
} from "@xingwen/ui/icons";

import { optionLabel, type ResearchOption } from "./research-contract-options";

type ContractSection = "goal" | "scope" | "data" | "outputs" | "quality";

interface ContractFormState {
  readonly intent: string;
  readonly researchGoal: string;
  readonly targetObjects: readonly string[];
  readonly requestedFields: readonly string[];
  readonly allowedSources: readonly string[];
  readonly keywords: readonly string[];
  readonly yearFrom: string;
  readonly yearTo: string;
  readonly sourceIds: readonly string[];
  readonly maxCandidates: string;
  readonly scientificTasks: readonly ScientificTaskInput[];
  readonly outputRequirements: readonly ArtifactKind[];
  readonly requireLocator: boolean;
  readonly requireSourceSnapshot: boolean;
  readonly minimumCoverage: string;
  readonly sourceCompletenessMin: string;
  readonly unitConsistencyMin: string;
}

interface ValidationIssue {
  readonly section: ContractSection;
  readonly field: keyof ContractFormState | "scopeInvariant";
  readonly message: string;
}

interface ResearchContractFormProps {
  readonly draft: ResearchContractDraftViewModel;
  readonly catalog: ResearchPlanningCatalog;
  readonly pendingAction: "save-draft" | "confirm-contract" | null;
  readonly errorMessage: string | null;
  readonly onSaveDraft: (
    intent: string,
    contract: ResearchContractInput,
  ) => Promise<void>;
  readonly onConfirmContract: () => Promise<void>;
  readonly onDirtyChange?: (dirty: boolean) => void;
}

const SECTIONS: readonly {
  readonly value: ContractSection;
  readonly label: string;
  readonly icon: LucideIcon;
}[] = [
  { value: "goal", label: "研究目标", icon: Target },
  { value: "scope", label: "研究范围", icon: ScanSearch },
  { value: "data", label: "数据与文献", icon: Database },
  { value: "outputs", label: "成果要求", icon: PackageCheck },
  { value: "quality", label: "证据与质量", icon: ShieldCheck },
];

function normalizeOutputOrder(selected: readonly ArtifactKind[]) {
  return [...new Set(selected)];
}

function updateOutputSelection(
  selected: readonly ArtifactKind[],
  value: ArtifactKind,
  checked: boolean,
) {
  const next = new Set(selected);
  if (checked) next.add(value);
  else next.delete(value);
  return normalizeOutputOrder([...next]);
}

function ProductMultiSelect({
  label,
  description,
  options,
  selected,
  disabled,
  error,
  onChange,
}: {
  readonly label: string;
  readonly description: string;
  readonly options: readonly ResearchOption[];
  readonly selected: readonly string[];
  readonly disabled: boolean;
  readonly error?: string;
  readonly onChange: (value: readonly string[]) => void;
}) {
  const toggle = (value: string) => {
    onChange(
      selected.includes(value)
        ? selected.filter((item) => item !== value)
        : [...selected, value],
    );
  };
  return (
    <Field data-invalid={Boolean(error)}>
      <FieldLabel>{label}</FieldLabel>
      <FieldDescription>{description}</FieldDescription>
      <Popover>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="secondary"
            className="research-multiselect__trigger"
            disabled={disabled}
          >
            <span>
              {selected.length > 0
                ? `已选择 ${selected.length} 项`
                : "选择内容"}
            </span>
            <ChevronDown aria-hidden="true" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="research-multiselect__popover">
          <Command>
            <CommandInput placeholder={`搜索${label}`} />
            <CommandList>
              <CommandEmpty>没有匹配项</CommandEmpty>
              <CommandGroup>
                {options.map((option) => {
                  const checked = selected.includes(option.value);
                  return (
                    <CommandItem
                      key={option.value}
                      value={option.label}
                      onSelect={() => toggle(option.value)}
                    >
                      <Check
                        className={checked ? "is-visible" : "is-hidden"}
                        aria-hidden="true"
                      />
                      <span className="research-multiselect__option">
                        <strong>{option.label}</strong>
                        <small>{option.description}</small>
                      </span>
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {selected.length > 0 ? (
        <div className="research-tags" aria-label={`已选${label}`}>
          {selected.map((value) => (
            <span className="research-tag" key={value}>
              {optionLabel(options, value)}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                disabled={disabled}
                aria-label={`移除${optionLabel(options, value)}`}
                onClick={() => toggle(value)}
              >
                <X aria-hidden="true" />
              </Button>
            </span>
          ))}
        </div>
      ) : null}
      {error ? <FieldError errors={[{ message: error }]} /> : null}
    </Field>
  );
}

function TagInput({
  id,
  label,
  description,
  placeholder,
  values,
  disabled,
  onChange,
}: {
  readonly id: string;
  readonly label: string;
  readonly description: string;
  readonly placeholder: string;
  readonly values: readonly string[];
  readonly disabled: boolean;
  readonly onChange: (value: readonly string[]) => void;
}) {
  const [draftValue, setDraftValue] = useState("");
  const add = () => {
    const value = draftValue.trim();
    if (!value || values.includes(value)) return;
    onChange([...values, value]);
    setDraftValue("");
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter" && event.key !== ",") return;
    event.preventDefault();
    add();
  };
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <FieldDescription>{description}</FieldDescription>
      <div className="research-tag-input">
        <Input
          id={id}
          value={draftValue}
          disabled={disabled}
          placeholder={placeholder}
          onChange={(event) => setDraftValue(event.currentTarget.value)}
          onKeyDown={onKeyDown}
          onBlur={add}
        />
        <Button
          type="button"
          variant="secondary"
          size="icon"
          disabled={disabled || !draftValue.trim()}
          aria-label={`添加${label}`}
          onClick={add}
        >
          <Plus aria-hidden="true" />
        </Button>
      </div>
      {values.length > 0 ? (
        <div className="research-tags" aria-label={label}>
          {values.map((value) => (
            <span className="research-tag" key={value}>
              {value}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                disabled={disabled}
                aria-label={`移除 ${value}`}
                onClick={() =>
                  onChange(values.filter((item) => item !== value))
                }
              >
                <X aria-hidden="true" />
              </Button>
            </span>
          ))}
        </div>
      ) : null}
    </Field>
  );
}

function OutputChoices({
  options,
  selected,
  disabled,
  onChange,
}: {
  readonly options: readonly (ResearchOption & {
    readonly value: ArtifactKind;
  })[];
  readonly selected: readonly ArtifactKind[];
  readonly disabled: boolean;
  readonly onChange: (value: readonly ArtifactKind[]) => void;
}) {
  return (
    <FieldGroup className="research-contract-form__outputs">
      {options.map((option) => {
        const checked = selected.includes(option.value);
        const inputId = `output-requirement-${option.value}`;
        return (
          <Field
            key={option.value}
            orientation="horizontal"
            data-selected={checked}
          >
            <Checkbox
              id={inputId}
              checked={checked}
              disabled={disabled}
              onCheckedChange={(next) =>
                onChange(
                  updateOutputSelection(selected, option.value, next === true),
                )
              }
            />
            <FieldContent>
              <FieldLabel htmlFor={inputId}>{option.label}</FieldLabel>
              <FieldDescription>{option.description}</FieldDescription>
            </FieldContent>
          </Field>
        );
      })}
    </FieldGroup>
  );
}

function formFromDraft(
  draft: ResearchContractDraftViewModel,
): ContractFormState {
  return {
    intent: draft.intent,
    researchGoal: draft.contract.researchGoal,
    targetObjects: [...draft.contract.targetObjects],
    requestedFields: [...draft.contract.requestedFields],
    allowedSources: [...draft.contract.sourceScope.allowedSources],
    keywords: [...draft.contract.paperSearchScope.keywords],
    yearFrom: draft.contract.paperSearchScope.yearFrom?.toString() ?? "",
    yearTo: draft.contract.paperSearchScope.yearTo?.toString() ?? "",
    sourceIds: [...draft.contract.paperSearchScope.sourceIds],
    maxCandidates: draft.contract.paperSearchScope.maxCandidates.toString(),
    scientificTasks: draft.contract.scientificTasks.map((task) => ({
      taskId: task.taskId,
      skillId: task.skillId,
      parameters: { ...task.parameters },
      inputRefs: [...task.inputRefs],
    })),
    outputRequirements: normalizeOutputOrder(draft.contract.outputRequirements),
    requireLocator: draft.contract.evidenceRequirements.requireLocator,
    requireSourceSnapshot:
      draft.contract.evidenceRequirements.requireSourceSnapshot,
    minimumCoverage: String(
      Math.round(draft.contract.evidenceRequirements.minimumCoverage * 100),
    ),
    sourceCompletenessMin: String(
      Math.round(draft.contract.qualityConstraints.sourceCompletenessMin * 100),
    ),
    unitConsistencyMin: String(
      Math.round(draft.contract.qualityConstraints.unitConsistencyMin * 100),
    ),
  };
}

function parseOptionalYear(value: string): number | null {
  return value.trim() ? Number(value) : null;
}

function parseContract(form: ContractFormState): {
  readonly input: ResearchContractInput | null;
  readonly issues: readonly ValidationIssue[];
} {
  const issues: ValidationIssue[] = [];
  const parseIdentifiers = (
    values: readonly string[],
    label: string,
    section: ContractSection,
    field: keyof ContractFormState,
  ) => {
    const parsed = values.map(parseEntityId);
    if (parsed.some((item) => item === null)) {
      issues.push({ section, field, message: `${label}中存在无效内容。` });
    }
    return parsed.filter((item) => item !== null);
  };
  const targetObjects = parseIdentifiers(
    form.targetObjects,
    "研究对象",
    "scope",
    "targetObjects",
  );
  const requestedFields = parseIdentifiers(
    form.requestedFields,
    "研究数据",
    "scope",
    "requestedFields",
  );
  const allowedSources = parseIdentifiers(
    form.allowedSources,
    "数据来源",
    "data",
    "allowedSources",
  );
  const sourceIds = parseIdentifiers(
    form.sourceIds,
    "文献标识",
    "data",
    "sourceIds",
  );
  const maxCandidates = Number(form.maxCandidates);
  const minimumCoverage = Number(form.minimumCoverage) / 100;
  const sourceCompletenessMin = Number(form.sourceCompletenessMin) / 100;
  const unitConsistencyMin = Number(form.unitConsistencyMin) / 100;
  const yearFrom = parseOptionalYear(form.yearFrom);
  const yearTo = parseOptionalYear(form.yearTo);

  if (!form.intent.trim()) {
    issues.push({
      section: "goal",
      field: "intent",
      message: "请填写研究问题。",
    });
  }
  if (form.researchGoal.trim().length < 4) {
    issues.push({
      section: "goal",
      field: "researchGoal",
      message: "研究目标至少需要 4 个字符。",
    });
  }
  if (targetObjects.length === 0) {
    issues.push({
      section: "scope",
      field: "targetObjects",
      message: "请至少选择一个研究对象。",
    });
  }
  if (requestedFields.length === 0) {
    issues.push({
      section: "scope",
      field: "requestedFields",
      message: "请至少选择一项研究数据。",
    });
  }
  if (allowedSources.length === 0) {
    issues.push({
      section: "data",
      field: "allowedSources",
      message: "请至少选择一个数据来源。",
    });
  }
  if (form.outputRequirements.length === 0) {
    issues.push({
      section: "outputs",
      field: "outputRequirements",
      message: "请至少选择一种研究成果。",
    });
  }
  if (
    !Number.isInteger(maxCandidates) ||
    maxCandidates < 1 ||
    maxCandidates > 100
  ) {
    issues.push({
      section: "data",
      field: "maxCandidates",
      message: "文献候选数量必须是 1–100 的整数。",
    });
  }
  for (const [field, value] of [
    ["minimumCoverage", minimumCoverage],
    ["sourceCompletenessMin", sourceCompletenessMin],
    ["unitConsistencyMin", unitConsistencyMin],
  ] as const) {
    if (!Number.isFinite(value) || value < 0 || value > 1) {
      issues.push({
        section: "quality",
        field,
        message: "请输入 0–100 之间的百分比。",
      });
    }
  }
  for (const [field, value] of [
    ["yearFrom", yearFrom],
    ["yearTo", yearTo],
  ] as const) {
    if (
      value !== null &&
      (!Number.isInteger(value) || value < 1900 || value > 9999)
    ) {
      issues.push({
        section: "data",
        field,
        message: "请输入 1900–9999 的整数年份。",
      });
    }
  }
  if (yearFrom !== null && yearTo !== null && yearFrom > yearTo) {
    issues.push({
      section: "data",
      field: "yearTo",
      message: "起始年份不能晚于结束年份。",
    });
  }

  const input: ResearchContractInput = {
    researchGoal: form.researchGoal.trim(),
    targetObjects,
    dataRequirements: { unitPolicy: "canonical" },
    requestedFields,
    sourceScope: { allowedSources },
    paperSearchScope: {
      keywords: form.keywords,
      yearFrom,
      yearTo,
      sourceIds,
      maxCandidates,
    },
    scientificTasks: form.scientificTasks,
    outputRequirements: form.outputRequirements,
    evidenceRequirements: {
      requireLocator: form.requireLocator,
      requireSourceSnapshot: form.requireSourceSnapshot,
      minimumCoverage,
    },
    qualityConstraints: { sourceCompletenessMin, unitConsistencyMin },
  };
  if (validateContractInputInvariants(input).length > 0) {
    issues.push({
      section: "scope",
      field: "scopeInvariant",
      message: "研究范围中存在相互冲突的设置，请检查后重试。",
    });
  }
  return { input: issues.length === 0 ? input : null, issues };
}

function FieldIssue({
  field,
  issues,
}: {
  readonly field: ValidationIssue["field"];
  readonly issues: readonly ValidationIssue[];
}) {
  const messages = issues
    .filter((issue) => issue.field === field)
    .map((issue) => ({ message: issue.message }));
  return messages.length > 0 ? <FieldError errors={messages} /> : null;
}

export function ResearchContractForm(props: ResearchContractFormProps) {
  const formKey = `${String(props.draft.id)}:${String(props.draft.version)}`;
  return <ResearchContractFormSurface key={formKey} {...props} />;
}

function ResearchContractFormSurface({
  draft,
  catalog,
  pendingAction,
  errorMessage,
  onSaveDraft,
  onConfirmContract,
  onDirtyChange,
}: ResearchContractFormProps) {
  const formRef = useRef<HTMLFormElement>(null);
  const [activeSection, setActiveSection] = useState<ContractSection>("goal");
  const [form, setForm] = useState(() => formFromDraft(draft));
  const [validationIssues, setValidationIssues] = useState<
    readonly ValidationIssue[]
  >([]);
  const baseline = useMemo(() => JSON.stringify(formFromDraft(draft)), [draft]);
  const dirty = JSON.stringify(form) !== baseline;
  const pending = pendingAction !== null;
  const commonOutputs = catalog.outputRequirements.filter(
    (option) => option.group === "common",
  );
  const advancedOutputs = catalog.outputRequirements.filter(
    (option) => option.group === "advanced",
  );

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  useEffect(
    () => () => {
      onDirtyChange?.(false);
    },
    [onDirtyChange],
  );

  const update = <K extends keyof ContractFormState>(
    key: K,
    value: ContractFormState[K],
  ) => {
    setForm((current) => ({ ...current, [key]: value }));
    setValidationIssues((current) =>
      current.filter(
        (issue) => issue.field !== key && issue.field !== "scopeInvariant",
      ),
    );
  };

  const issueFor = (field: ValidationIssue["field"]) =>
    validationIssues.find((issue) => issue.field === field)?.message;

  const selectSection = (section: ContractSection) => {
    setActiveSection(section);
    requestAnimationFrame(() => {
      formRef.current
        ?.querySelector<HTMLElement>('[data-slot="scroll-area-viewport"]')
        ?.scrollTo({ top: 0 });
    });
  };

  const submitDraft = async () => {
    const parsed = parseContract(form);
    setValidationIssues(parsed.issues);
    if (!parsed.input) {
      setActiveSection(parsed.issues[0]?.section ?? "goal");
      requestAnimationFrame(() => {
        formRef.current
          ?.querySelector<HTMLElement>(
            '[aria-invalid="true"], [data-invalid="true"] button, input',
          )
          ?.focus();
      });
      return;
    }
    await onSaveDraft(form.intent.trim(), parsed.input);
  };

  return (
    <form
      ref={formRef}
      className="research-contract-form"
      aria-label="研究协议草稿"
      onSubmit={(event) => event.preventDefault()}
    >
      <Tabs
        value={activeSection}
        onValueChange={(value) => selectSection(value as ContractSection)}
        orientation="horizontal"
        className="research-contract-form__tabs"
      >
        <TabsList variant="line" aria-label="研究协议分区">
          {SECTIONS.map((section) => (
            <TabsTrigger key={section.value} value={section.value}>
              <section.icon aria-hidden="true" />
              {section.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <ScrollArea className="research-contract-form__editor">
          <div className="research-contract-form__editor-content">
            <TabsContent value="goal">
              <FieldGroup>
                <div className="research-contract-form__section-heading">
                  <h3>研究目标</h3>
                  <p>确认助手正在回答的问题，以及本次研究的可验证目标。</p>
                </div>
                <Field data-invalid={Boolean(issueFor("intent"))}>
                  <FieldLabel htmlFor="contract-intent">研究问题</FieldLabel>
                  <FieldDescription>
                    保留用户最初提出的问题，不自动扩写为执行协议。
                  </FieldDescription>
                  <Textarea
                    id="contract-intent"
                    value={form.intent}
                    disabled={pending}
                    aria-invalid={Boolean(issueFor("intent"))}
                    onChange={(event) =>
                      update("intent", event.currentTarget.value)
                    }
                  />
                  <FieldIssue field="intent" issues={validationIssues} />
                </Field>
                <Field data-invalid={Boolean(issueFor("researchGoal"))}>
                  <FieldLabel htmlFor="research-goal">预期回答</FieldLabel>
                  <FieldDescription>
                    用一句话描述完成研究后应该能够验证的结论或成果。
                  </FieldDescription>
                  <Textarea
                    id="research-goal"
                    value={form.researchGoal}
                    disabled={pending}
                    aria-invalid={Boolean(issueFor("researchGoal"))}
                    maxLength={500}
                    placeholder="例如：建立可追溯的宿主恒星参数比较集"
                    onChange={(event) =>
                      update("researchGoal", event.currentTarget.value)
                    }
                  />
                  <FieldIssue field="researchGoal" issues={validationIssues} />
                </Field>
              </FieldGroup>
            </TabsContent>

            <TabsContent value="scope">
              <FieldGroup>
                <div className="research-contract-form__section-heading">
                  <h3>研究范围</h3>
                  <p>选择本次研究覆盖的对象和需要比较的数据。</p>
                </div>
                <ProductMultiSelect
                  label="研究对象"
                  description="选择需要纳入研究的天体类型。"
                  options={catalog.targetObjects}
                  selected={form.targetObjects}
                  disabled={pending}
                  error={issueFor("targetObjects")}
                  onChange={(value) => update("targetObjects", value)}
                />
                <ProductMultiSelect
                  label="研究数据"
                  description="选择需要采集、比较或追溯的观测参数。"
                  options={catalog.requestedFields}
                  selected={form.requestedFields}
                  disabled={pending}
                  error={issueFor("requestedFields")}
                  onChange={(value) => update("requestedFields", value)}
                />
                <FieldIssue field="scopeInvariant" issues={validationIssues} />
              </FieldGroup>
            </TabsContent>

            <TabsContent value="data">
              <FieldGroup>
                <div className="research-contract-form__section-heading">
                  <h3>数据与文献</h3>
                  <p>限定可使用的数据来源与文献检索范围。</p>
                </div>
                <ProductMultiSelect
                  label="数据来源"
                  description="只显示当前研究案例已经批准的公开来源。"
                  options={catalog.allowedSources}
                  selected={form.allowedSources}
                  disabled={pending}
                  error={issueFor("allowedSources")}
                  onChange={(value) => update("allowedSources", value)}
                />
                <TagInput
                  id="keywords"
                  label="检索关键词"
                  description="输入关键词后按 Enter 添加，可保留多个研究概念。"
                  placeholder="例如：宿主恒星金属丰度"
                  values={form.keywords}
                  disabled={pending}
                  onChange={(value) => update("keywords", value)}
                />
                <div className="research-contract-form__grid">
                  <Field data-invalid={Boolean(issueFor("yearFrom"))}>
                    <FieldLabel htmlFor="year-from">起始年份</FieldLabel>
                    <Input
                      id="year-from"
                      type="number"
                      min={1900}
                      max={9999}
                      value={form.yearFrom}
                      disabled={pending}
                      aria-invalid={Boolean(issueFor("yearFrom"))}
                      onChange={(event) =>
                        update("yearFrom", event.currentTarget.value)
                      }
                    />
                    <FieldIssue field="yearFrom" issues={validationIssues} />
                  </Field>
                  <Field data-invalid={Boolean(issueFor("yearTo"))}>
                    <FieldLabel htmlFor="year-to">结束年份</FieldLabel>
                    <Input
                      id="year-to"
                      type="number"
                      min={1900}
                      max={9999}
                      value={form.yearTo}
                      disabled={pending}
                      aria-invalid={Boolean(issueFor("yearTo"))}
                      onChange={(event) =>
                        update("yearTo", event.currentTarget.value)
                      }
                    />
                    <FieldIssue field="yearTo" issues={validationIssues} />
                  </Field>
                  <Field data-invalid={Boolean(issueFor("maxCandidates"))}>
                    <FieldLabel htmlFor="max-candidates">
                      文献候选数量
                    </FieldLabel>
                    <Input
                      id="max-candidates"
                      type="number"
                      min={1}
                      max={100}
                      value={form.maxCandidates}
                      disabled={pending}
                      aria-invalid={Boolean(issueFor("maxCandidates"))}
                      onChange={(event) =>
                        update("maxCandidates", event.currentTarget.value)
                      }
                    />
                    <FieldIssue
                      field="maxCandidates"
                      issues={validationIssues}
                    />
                  </Field>
                </div>
                <Collapsible className="research-contract-form__advanced">
                  <CollapsibleTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="small"
                      className="research-contract-form__advanced-trigger"
                    >
                      <ChevronRight
                        data-icon="inline-start"
                        aria-hidden="true"
                      />
                      限定文献标识
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <TagInput
                      id="source-ids"
                      label="指定文献标识"
                      description="仅在需要限定特定 DOI 或来源标识时填写。"
                      placeholder="输入标识后按 Enter"
                      values={form.sourceIds}
                      disabled={pending}
                      onChange={(value) => update("sourceIds", value)}
                    />
                    <FieldIssue field="sourceIds" issues={validationIssues} />
                  </CollapsibleContent>
                </Collapsible>
              </FieldGroup>
            </TabsContent>

            <TabsContent value="outputs">
              <FieldGroup>
                <div className="research-contract-form__section-heading">
                  <h3>成果要求</h3>
                  <p>选择本次研究需要交付的成果，可多选。</p>
                </div>
                {form.scientificTasks.length > 0 ? (
                  <FieldSet className="research-contract-form__scientific-tasks">
                    <FieldLegend>已规划科学任务</FieldLegend>
                    <p>
                      任务参数由规划器冻结；修改研究目标后会生成新的协议草稿。
                    </p>
                    <ol>
                      {form.scientificTasks.map((task) => {
                        const option = catalog.scientificSkills.find(
                          (item) => item.value === task.skillId,
                        );
                        return (
                          <li key={task.taskId}>
                            <strong>{option?.label ?? task.skillId}</strong>
                            <span>{option?.description ?? task.taskId}</span>
                          </li>
                        );
                      })}
                    </ol>
                  </FieldSet>
                ) : null}
                <FieldSet className="research-contract-form__output-group">
                  <FieldLegend className="research-contract-form__output-group-title">
                    常用成果
                  </FieldLegend>
                  <OutputChoices
                    options={commonOutputs}
                    selected={form.outputRequirements}
                    disabled={pending}
                    onChange={(value) => update("outputRequirements", value)}
                  />
                  <FieldIssue
                    field="outputRequirements"
                    issues={validationIssues}
                  />
                </FieldSet>
                <Collapsible className="research-contract-form__advanced">
                  <CollapsibleTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="small"
                      className="research-contract-form__advanced-trigger"
                    >
                      <ChevronRight
                        data-icon="inline-start"
                        aria-hidden="true"
                      />
                      高级研究成果
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <OutputChoices
                      options={advancedOutputs}
                      selected={form.outputRequirements}
                      disabled={pending}
                      onChange={(value) => update("outputRequirements", value)}
                    />
                  </CollapsibleContent>
                </Collapsible>
              </FieldGroup>
            </TabsContent>

            <TabsContent value="quality">
              <FieldGroup>
                <div className="research-contract-form__section-heading">
                  <h3>证据与质量</h3>
                  <p>设置结果需要达到的可追溯性和数据质量目标。</p>
                </div>
                <label className="research-contract-form__check-row">
                  <Checkbox
                    checked={form.requireLocator}
                    disabled={pending}
                    onCheckedChange={(value) =>
                      update("requireLocator", value === true)
                    }
                  />
                  <span>
                    <strong>保留证据定位</strong>
                    <small>记录结果对应的数据行、字段或文献位置。</small>
                  </span>
                </label>
                <label className="research-contract-form__check-row">
                  <Checkbox
                    checked={form.requireSourceSnapshot}
                    disabled={pending}
                    onCheckedChange={(value) =>
                      update("requireSourceSnapshot", value === true)
                    }
                  />
                  <span>
                    <strong>保留来源快照</strong>
                    <small>保存研究时实际使用的来源状态。</small>
                  </span>
                </label>
                <div className="research-contract-form__grid">
                  <Field data-invalid={Boolean(issueFor("minimumCoverage"))}>
                    <FieldLabel htmlFor="minimum-coverage">
                      最低证据覆盖率（%）
                    </FieldLabel>
                    <Input
                      id="minimum-coverage"
                      type="number"
                      min={0}
                      max={100}
                      value={form.minimumCoverage}
                      disabled={pending}
                      aria-invalid={Boolean(issueFor("minimumCoverage"))}
                      onChange={(event) =>
                        update("minimumCoverage", event.currentTarget.value)
                      }
                    />
                    <FieldIssue
                      field="minimumCoverage"
                      issues={validationIssues}
                    />
                  </Field>
                  <Field
                    data-invalid={Boolean(issueFor("sourceCompletenessMin"))}
                  >
                    <FieldLabel htmlFor="source-completeness">
                      来源完整性目标（%）
                    </FieldLabel>
                    <Input
                      id="source-completeness"
                      type="number"
                      min={0}
                      max={100}
                      value={form.sourceCompletenessMin}
                      disabled={pending}
                      aria-invalid={Boolean(issueFor("sourceCompletenessMin"))}
                      onChange={(event) =>
                        update(
                          "sourceCompletenessMin",
                          event.currentTarget.value,
                        )
                      }
                    />
                    <FieldIssue
                      field="sourceCompletenessMin"
                      issues={validationIssues}
                    />
                  </Field>
                  <Field data-invalid={Boolean(issueFor("unitConsistencyMin"))}>
                    <FieldLabel htmlFor="unit-consistency">
                      单位一致性目标（%）
                    </FieldLabel>
                    <Input
                      id="unit-consistency"
                      type="number"
                      min={0}
                      max={100}
                      value={form.unitConsistencyMin}
                      disabled={pending}
                      aria-invalid={Boolean(issueFor("unitConsistencyMin"))}
                      onChange={(event) =>
                        update("unitConsistencyMin", event.currentTarget.value)
                      }
                    />
                    <FieldIssue
                      field="unitConsistencyMin"
                      issues={validationIssues}
                    />
                  </Field>
                </div>
              </FieldGroup>
            </TabsContent>
          </div>
        </ScrollArea>
      </Tabs>

      <div className="research-contract-form__actions">
        {errorMessage ? (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        ) : null}
        <span className="research-contract-form__save-state">
          {dirty ? "有未保存修改" : "草稿已保存，可确认协议"}
        </span>
        <div>
          <Button
            type="button"
            variant="secondary"
            disabled={pending || !dirty}
            onClick={() => void submitDraft()}
          >
            {pendingAction === "save-draft" ? "正在保存…" : "保存草稿"}
          </Button>
          <Button
            type="button"
            disabled={pending || dirty}
            onClick={() => void onConfirmContract()}
          >
            {pendingAction === "confirm-contract"
              ? "正在确认…"
              : "确认研究协议"}
          </Button>
        </div>
      </div>
    </form>
  );
}
