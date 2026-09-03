import { useMutation, useQuery } from "@tanstack/react-query";
import type { AcquirePaperFullTextInput } from "@xingwen/data-access/ports";
import { safeExternalUrl, type DomainEntityId } from "@xingwen/domain";
import {
  Alert,
  AlertDescription,
  Button,
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
  Input,
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
  ToggleGroup,
  ToggleGroupItem,
} from "@xingwen/ui";
import { Download, FileCheck2, LoaderCircle } from "@xingwen/ui/icons";
import { useId, useState } from "react";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";

type AccessKind = AcquirePaperFullTextInput["accessKind"];
const ACCESS_KINDS: readonly { value: AccessKind; label: string }[] = [
  { value: "publisher_open_access", label: "出版方开放全文" },
  { value: "repository_open_access", label: "开放存储库" },
  { value: "author_provided", label: "作者公开提供" },
];

export function PaperFullTextForm({
  runtime,
  projectId,
  artifactVersionId,
  candidateId,
  canonicalPaperId,
  sourceUrl,
  isLive,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifactVersionId: DomainEntityId;
  readonly candidateId: DomainEntityId;
  readonly canonicalPaperId: DomainEntityId;
  readonly sourceUrl: string | null;
  readonly isLive: boolean;
}) {
  const id = useId();
  const [mode, setMode] = useState<"open_access" | "uploaded">(
    isLive ? "open_access" : "uploaded",
  );
  const [accessUrl, setAccessUrl] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState(sourceUrl ?? "");
  const [accessKind, setAccessKind] = useState<AccessKind>(
    "publisher_open_access",
  );
  const [license, setLicense] = useState("");
  const [selectedInputId, setSelectedInputId] = useState<string>("");
  const inputs = useQuery({
    ...runtime.application.queries.researchInputs(projectId),
    enabled: mode === "uploaded",
  });
  const documents = (inputs.data ?? []).filter(
    (input) =>
      input.status === "accepted" &&
      (input.type === "pdf" ||
        input.type === "image" ||
        input.mimeType === "application/pdf" ||
        ["image/jpeg", "image/png", "image/tiff", "image/webp"].includes(
          input.mimeType ?? "",
        )),
  );
  const selectedInput = documents.find((input) => input.id === selectedInputId);
  const binding = useMutation(
    runtime.application.mutations.paperFullTextAttach(),
  );

  return (
    <form
      className="paper-collection-workspace__binding"
      aria-label="关联论文全文"
      onChange={() => binding.reset()}
      onSubmit={(event) => {
        event.preventDefault();
        const common = {
          projectId,
          artifactVersionId,
          candidateId,
          canonicalPaperId,
          evidenceUrl: evidenceUrl.trim(),
        };
        if (mode === "open_access") {
          binding.mutate({
            ...common,
            mode,
            accessUrl: accessUrl.trim(),
            accessKind,
            license: license.trim(),
          });
        } else if (selectedInput) {
          binding.mutate({
            ...common,
            mode,
            researchInputId: selectedInput.id,
            researchInputContentHash: selectedInput.contentHash,
          });
        }
      }}
    >
      <FieldSet disabled={binding.isPending}>
        <FieldLegend variant="label">论文全文</FieldLegend>
        <FieldDescription>
          关联后，通过“基于此结果重新分析”生成带页码与段落定位的文献结论。
        </FieldDescription>
        <ToggleGroup
          type="single"
          variant="segmented"
          size="sm"
          aria-label="全文来源方式"
          value={mode}
          onValueChange={(value) => {
            if (value === "open_access" || value === "uploaded") {
              setMode(value);
              binding.reset();
            }
          }}
        >
          <ToggleGroupItem
            value="open_access"
            disabled={!isLive || binding.isPending}
          >
            开放全文链接
          </ToggleGroupItem>
          <ToggleGroupItem value="uploaded" disabled={binding.isPending}>
            已上传文档
          </ToggleGroupItem>
        </ToggleGroup>
        {!isLive ? (
          <FieldDescription>演示结果不执行真实全文获取。</FieldDescription>
        ) : null}
        <FieldGroup className="paper-full-text-fields">
          {mode === "open_access" ? (
            <>
              <Field>
                <FieldLabel htmlFor={`${id}-url`}>全文地址</FieldLabel>
                <Input
                  id={`${id}-url`}
                  type="url"
                  required
                  pattern="https://.+"
                  maxLength={2048}
                  placeholder="https://…/article.pdf"
                  value={accessUrl}
                  onChange={(event) => setAccessUrl(event.target.value)}
                />
                <FieldDescription>
                  填写有权访问的 PDF 直链，不使用付费墙或登录凭据。
                </FieldDescription>
              </Field>
              <Field>
                <FieldLabel htmlFor={`${id}-kind`}>开放来源</FieldLabel>
                <Select
                  value={accessKind}
                  disabled={binding.isPending}
                  onValueChange={(value) => {
                    const kind = ACCESS_KINDS.find(
                      (item) => item.value === value,
                    );
                    if (kind) setAccessKind(kind.value);
                  }}
                >
                  <SelectTrigger id={`${id}-kind`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {ACCESS_KINDS.map((kind) => (
                        <SelectItem key={kind.value} value={kind.value}>
                          {kind.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor={`${id}-license`}>
                  许可或开放获取依据
                </FieldLabel>
                <Input
                  id={`${id}-license`}
                  required
                  maxLength={256}
                  value={license}
                  placeholder="按来源页面如实填写许可或开放说明"
                  onChange={(event) => setLicense(event.target.value)}
                />
              </Field>
            </>
          ) : (
            <Field>
              <FieldLabel htmlFor={`${id}-document`}>已上传科研文档</FieldLabel>
              {inputs.isPending ? (
                <FieldDescription>正在读取项目资料…</FieldDescription>
              ) : inputs.isError ? (
                <Alert variant="destructive">
                  <AlertDescription>
                    {
                      runtime.researchAdapter.toPublicApplicationError(
                        inputs.error,
                      ).safeMessage
                    }
                    <Button
                      type="button"
                      variant="secondary"
                      size="small"
                      onClick={() => void inputs.refetch()}
                    >
                      重新读取资料
                    </Button>
                  </AlertDescription>
                </Alert>
              ) : documents.length > 0 ? (
                <Select
                  value={selectedInputId}
                  disabled={binding.isPending}
                  onValueChange={setSelectedInputId}
                  required
                >
                  <SelectTrigger id={`${id}-document`}>
                    <SelectValue placeholder="选择 PDF 或论文图像" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {documents.map((document) => (
                        <SelectItem key={document.id} value={document.id}>
                          {document.filename ?? "未命名文档"}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              ) : (
                <FieldDescription>
                  暂无可绑定文档。返回研究，在消息输入框上传 PDF
                  或论文图像后重试。
                </FieldDescription>
              )}
            </Field>
          )}
          <Field>
            <FieldLabel htmlFor={`${id}-evidence`}>
              {mode === "open_access" ? "开放获取说明页面" : "论文来源页面"}
            </FieldLabel>
            <Input
              id={`${id}-evidence`}
              type="url"
              required
              pattern="https://.+"
              maxLength={2048}
              placeholder="https://…"
              value={evidenceUrl}
              onChange={(event) => setEvidenceUrl(event.target.value)}
            />
          </Field>
        </FieldGroup>
        <div className="paper-collection-workspace__binding-controls">
          <Button
            type="submit"
            size="small"
            disabled={
              binding.isPending ||
              binding.isSuccess ||
              !safeExternalUrl(evidenceUrl) ||
              (mode === "uploaded" && !selectedInput)
            }
          >
            {binding.isPending ? (
              <LoaderCircle
                className="motion-safe:animate-spin"
                data-icon="inline-start"
                aria-hidden="true"
              />
            ) : mode === "open_access" ? (
              <Download data-icon="inline-start" aria-hidden="true" />
            ) : (
              <FileCheck2 data-icon="inline-start" aria-hidden="true" />
            )}
            {binding.isPending
              ? "正在关联全文…"
              : mode === "open_access"
                ? "获取并关联全文"
                : "确认绑定全文"}
          </Button>
        </div>
      </FieldSet>
      {binding.isSuccess ? (
        <FieldDescription role="status">
          {binding.data.status === "accepted"
            ? "全文已关联。重新分析后可查看文档证据。"
            : "资料已保存，但当前格式无法解析。请改用可访问的 PDF 或论文图像。"}
        </FieldDescription>
      ) : null}
      {binding.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            {
              runtime.researchAdapter.toPublicApplicationError(binding.error)
                .safeMessage
            }
          </AlertDescription>
        </Alert>
      ) : null}
    </form>
  );
}
