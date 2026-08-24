import { useMutation, useQuery } from "@tanstack/react-query";
import type { ModelProviderPreset } from "@xingwen/domain";
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  toast,
} from "@xingwen/ui";
import {
  CheckCircle2,
  Eye,
  EyeOff,
  LoaderCircle,
  Settings2,
  ShieldCheck,
  TriangleAlert,
} from "@xingwen/ui/icons";
import { useState, type FormEvent } from "react";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";

const PRESET_OPTIONS: ReadonlyArray<{
  readonly value: ModelProviderPreset;
  readonly label: string;
}> = [
  { value: "dashscope", label: "阿里云百炼（Qwen）" },
  { value: "custom", label: "自定义 OpenAI 兼容接口" },
];

function safeError(
  runtime: WorkspaceRuntimeBoundaries,
  error: unknown,
): string {
  return runtime.researchAdapter.toPublicApplicationError(error).safeMessage;
}

export function ModelProviderControl({
  runtime,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
}) {
  const configuration = useQuery(
    runtime.application.queries.modelProviderConfiguration(),
  );
  const configure = useMutation(
    runtime.application.mutations.modelProviderConfigure(),
  );
  const remove = useMutation(
    runtime.application.mutations.modelProviderRemove(),
  );
  const [open, setOpen] = useState(false);
  const [removeOpen, setRemoveOpen] = useState(false);
  const [preset, setPreset] = useState<ModelProviderPreset>("dashscope");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [revealKey, setRevealKey] = useState(false);

  const current = configuration.data ?? null;
  const isReady = current?.status === "ready";
  const isDeploymentManaged = current?.source === "deployment";
  const editable = current?.editable ?? false;
  const error = configure.error
    ? safeError(runtime, configure.error)
    : remove.error
      ? safeError(runtime, remove.error)
      : null;

  const openDialog = () => {
    setPreset(current?.preset ?? "dashscope");
    setBaseUrl(current?.preset === "custom" ? (current.baseUrl ?? "") : "");
    setModel(current?.model ?? "");
    setApiKey("");
    configure.reset();
    remove.reset();
    setOpen(true);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      const next = await configure.mutateAsync({
        input: {
          preset,
          baseUrl: preset === "custom" ? baseUrl.trim() || null : null,
          model: model.trim(),
          apiKey,
        },
        expectedRevision: current?.revision ?? 0,
      });
      setApiKey("");
      setRevealKey(false);
      setOpen(false);
      toast.success(`已连接 ${next.model ?? "模型服务"}`);
    } catch {
      // The mutation owns the public error state rendered in the form.
    }
  };

  const removeConfiguration = async () => {
    try {
      await remove.mutateAsync(current?.revision ?? 0);
      setRemoveOpen(false);
      setOpen(false);
      toast.success("已移除工作台模型配置");
    } catch {
      // The mutation owns the public error state rendered in the form.
    }
  };

  const triggerLabel = configuration.isPending
    ? "正在检查模型服务"
    : isReady
      ? "模型服务已连接"
      : "配置模型服务";
  const displayedBaseUrl =
    preset === "dashscope" ? (current?.dashscopeBaseUrl ?? "") : baseUrl;

  return (
    <>
      <Button
        variant="ghost"
        size="small"
        className="model-provider-trigger"
        aria-label={triggerLabel}
        onClick={openDialog}
      >
        {configuration.isPending ? (
          <LoaderCircle aria-hidden="true" />
        ) : isReady ? (
          <ShieldCheck aria-hidden="true" />
        ) : (
          <Settings2 aria-hidden="true" />
        )}
        <span className="model-provider-trigger__label">模型服务</span>
        <span
          className="model-provider-trigger__state"
          data-ready={isReady}
          aria-hidden="true"
        />
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="model-provider-dialog">
          <DialogHeader>
            <DialogTitle>模型服务</DialogTitle>
            <DialogDescription>
              配置供此工作台的所有项目共用。
            </DialogDescription>
          </DialogHeader>

          {configuration.isError ? (
            <Alert variant="destructive">
              <TriangleAlert aria-hidden="true" />
              <AlertTitle>无法读取连接状态</AlertTitle>
              <AlertDescription>
                {safeError(runtime, configuration.error)}
              </AlertDescription>
              <Button
                variant="secondary"
                size="small"
                onClick={() => void configuration.refetch()}
              >
                重试
              </Button>
            </Alert>
          ) : isDeploymentManaged ? (
            <Alert>
              <ShieldCheck aria-hidden="true" />
              <AlertTitle>部署环境已配置</AlertTitle>
              <AlertDescription>
                {current?.model ?? "模型服务"} ·{" "}
                {current?.baseUrl ?? current?.dashscopeBaseUrl} · 工作台只读
              </AlertDescription>
            </Alert>
          ) : isReady ? (
            <Alert>
              <CheckCircle2 aria-hidden="true" />
              <AlertTitle>已连接</AlertTitle>
              <AlertDescription>
                {current?.model} · {current?.apiKeyHint}
              </AlertDescription>
            </Alert>
          ) : !editable ? (
            <Alert>
              <ShieldCheck aria-hidden="true" />
              <AlertTitle>需要部署管理员配置</AlertTitle>
              <AlertDescription>
                当前环境不允许匿名工作台修改全局模型服务。请由部署管理员设置服务端凭据。
              </AlertDescription>
            </Alert>
          ) : null}

          {!isDeploymentManaged && !configuration.isError && editable ? (
            <form className="model-provider-form" onSubmit={submit}>
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="model-provider-preset">
                    连接方式
                  </FieldLabel>
                  <Select
                    value={preset}
                    onValueChange={(value) =>
                      setPreset(value as ModelProviderPreset)
                    }
                    disabled={!editable}
                  >
                    <SelectTrigger id="model-provider-preset">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PRESET_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {preset === "custom" ? (
                    <FieldDescription>
                      远程主机需由部署管理员放行；仅验证 Chat Completions
                      兼容性。
                    </FieldDescription>
                  ) : null}
                </Field>

                <Field>
                  <FieldLabel htmlFor="model-provider-base-url">
                    Base URL
                  </FieldLabel>
                  <Input
                    id="model-provider-base-url"
                    inputMode="url"
                    autoComplete="url"
                    value={displayedBaseUrl}
                    onChange={(event) => setBaseUrl(event.target.value)}
                    placeholder="https://example.com/v1"
                    required
                    readOnly={preset === "dashscope"}
                    disabled={!editable}
                  />
                </Field>

                <Field>
                  <FieldLabel htmlFor="model-provider-model">
                    模型 ID
                  </FieldLabel>
                  <Input
                    id="model-provider-model"
                    value={model}
                    onChange={(event) => setModel(event.target.value)}
                    placeholder={
                      preset === "dashscope"
                        ? "输入你的 Qwen 模型 ID"
                        : "输入接口提供的模型 ID"
                    }
                    autoComplete="off"
                    required
                    disabled={!editable}
                  />
                </Field>

                <Field>
                  <FieldLabel htmlFor="model-provider-api-key">
                    API 密钥
                  </FieldLabel>
                  <div className="model-provider-secret-field">
                    <Input
                      id="model-provider-api-key"
                      type={revealKey ? "text" : "password"}
                      value={apiKey}
                      onChange={(event) => setApiKey(event.target.value)}
                      autoComplete="new-password"
                      required
                      disabled={!editable}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      aria-label={revealKey ? "隐藏 API 密钥" : "显示 API 密钥"}
                      className="model-provider-secret-field__toggle"
                      onClick={() => setRevealKey((value) => !value)}
                      disabled={!editable}
                    >
                      {revealKey ? (
                        <EyeOff aria-hidden="true" />
                      ) : (
                        <Eye aria-hidden="true" />
                      )}
                    </Button>
                  </div>
                  <FieldDescription>
                    仅加密保存在服务端，保存后不回显。
                  </FieldDescription>
                  <FieldError>{error}</FieldError>
                </Field>
              </FieldGroup>

              <DialogFooter className="model-provider-dialog__footer">
                {current?.source === "workspace" && editable ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="small"
                    onClick={() => setRemoveOpen(true)}
                  >
                    移除工作台配置
                  </Button>
                ) : (
                  <span />
                )}
                <div className="model-provider-dialog__primary-actions">
                  {!isReady ? (
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => setOpen(false)}
                    >
                      后续配置
                    </Button>
                  ) : null}
                  <Button
                    type="submit"
                    disabled={
                      !editable ||
                      configure.isPending ||
                      !model.trim() ||
                      !apiKey.trim() ||
                      (preset === "custom" && !baseUrl.trim())
                    }
                  >
                    {configure.isPending ? (
                      <LoaderCircle aria-hidden="true" />
                    ) : null}
                    {configure.isPending ? "正在测试" : "测试并保存"}
                  </Button>
                </div>
              </DialogFooter>
            </form>
          ) : (
            <DialogFooter>
              <Button variant="secondary" onClick={() => setOpen(false)}>
                完成
              </Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog open={removeOpen} onOpenChange={setRemoveOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>移除工作台模型配置？</AlertDialogTitle>
            <AlertDialogDescription>
              新的研究请求将停止使用这组凭据；已有结果不会被删除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>保留配置</AlertDialogCancel>
            <AlertDialogAction
              disabled={remove.isPending}
              onClick={() => void removeConfiguration()}
            >
              {remove.isPending ? "正在移除" : "确认移除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
