import { useMutation, useQuery } from "@tanstack/react-query";
import type {
  CreateResearchInputDraft,
  DomainEntityId,
  ResearchInputRef,
  ResearchInputType,
} from "@xingwen/domain";
import {
  Alert,
  AlertDescription,
  Badge,
  Button,
  Field,
  FieldDescription,
  FieldLabel,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
} from "@xingwen/ui";
import { Plus, RotateCcw } from "@xingwen/ui/icons";
import { useRef, useState, type FormEvent } from "react";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";

const FILE_ACCEPT = [
  ".pdf",
  ".csv",
  ".xlsx",
  ".parquet",
  ".json",
  ".zip",
  ".fits",
  ".fit",
  ".fts",
  ".txt",
  ".md",
  ".markdown",
  "image/*",
  "application/zip",
].join(",");

const FILE_TYPE_BY_EXTENSION: Readonly<Record<string, ResearchInputType>> = {
  pdf: "pdf",
  csv: "csv",
  xlsx: "xlsx",
  parquet: "parquet",
  json: "json",
  zip: "image_dataset",
  fits: "fits",
  fit: "fits",
  fts: "fits",
  txt: "text",
  md: "text",
  markdown: "text",
};

function resolveFileType(file: File): ResearchInputType | null {
  if (file.type.startsWith("image/")) return "image";
  const extension = file.name.split(".").at(-1)?.toLowerCase() ?? "";
  return FILE_TYPE_BY_EXTENSION[extension] ?? null;
}

function semanticTextMime(fileName: string, browserMime: string): string {
  const extension = fileName.split(".").at(-1)?.toLowerCase();
  if (extension === "md" || extension === "markdown") {
    return browserMime === "text/x-markdown"
      ? "text/x-markdown"
      : "text/markdown";
  }
  return "text/plain";
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function statusLabel(status: ResearchInputRef["status"]): string {
  if (status === "accepted") return "已接收";
  if (status === "unsupported_processing") return "暂不支持处理";
  if (status === "failed_ingestion") return "入库失败";
  return "状态未知";
}

function statusVariant(
  status: ResearchInputRef["status"],
): "secondary" | "outline" | "destructive" {
  if (status === "accepted") return "secondary";
  if (status === "failed_ingestion") return "destructive";
  return "outline";
}

function ResearchInputList({
  inputs,
}: {
  readonly inputs: readonly ResearchInputRef[];
}) {
  if (inputs.length === 0) {
    return (
      <p className="research-input-panel__empty">当前 Project 尚无研究输入。</p>
    );
  }
  return (
    <ul className="research-input-panel__list" aria-label="Project 研究输入">
      {inputs.map((input) => (
        <li key={input.id} data-status={input.status ?? "unknown"}>
          <div>
            <strong>{input.filename ?? `${input.type} 输入`}</strong>
            <span>
              <Badge variant="outline">{input.type}</Badge>
              <Badge variant={statusVariant(input.status)}>
                {statusLabel(input.status)}
              </Badge>
            </span>
          </div>
          <dl>
            <div>
              <dt>大小</dt>
              <dd>{formatBytes(input.sizeBytes)}</dd>
            </div>
            <div>
              <dt>MIME</dt>
              <dd>{input.mimeType ?? "未提供"}</dd>
            </div>
          </dl>
        </li>
      ))}
    </ul>
  );
}

export function ResearchInputPanel({
  runtime,
  projectId,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
}) {
  const inputs = useQuery(
    runtime.application.queries.researchInputs(projectId),
  );
  const createInput = useMutation(
    runtime.application.mutations.researchInputCreate(),
  );
  const [textContent, setTextContent] = useState("");
  const [textFormat, setTextFormat] = useState<"plain" | "markdown">("plain");
  const [textFilename, setTextFilename] = useState("");
  const [url, setUrl] = useState("");
  const [urlFilename, setUrlFilename] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const create = async (input: CreateResearchInputDraft) => {
    setLocalError(null);
    await createInput.mutateAsync({ input });
  };
  const submitText = (event: FormEvent) => {
    event.preventDefault();
    const content = textContent.trim();
    if (!content) return;
    const markdown = textFormat === "markdown";
    void create({
      type: "text",
      projectId,
      textContent: content,
      filename: textFilename.trim() || (markdown ? "input.md" : "input.txt"),
      mimeType: markdown ? "text/markdown" : "text/plain",
    }).then(
      () => {
        setTextContent("");
        setTextFilename("");
      },
      () => undefined,
    );
  };
  const submitUrl = (event: FormEvent) => {
    event.preventDefault();
    if (!url.trim()) return;
    void create({
      type: "url",
      projectId,
      url: url.trim(),
      filename: urlFilename.trim() || null,
      mimeType: null,
    }).then(
      () => {
        setUrl("");
        setUrlFilename("");
      },
      () => undefined,
    );
  };
  const submitFile = (event: FormEvent) => {
    event.preventDefault();
    if (file === null) return;
    const type = resolveFileType(file);
    if (type === null || type === "url") {
      setLocalError(
        "不支持该文件类型；请选择 PDF、CSV、XLSX、Parquet、JSON、图像、图像数据集 ZIP、FITS 或文本/Markdown。",
      );
      return;
    }
    void (async () => {
      if (type === "text") {
        await create({
          type: "text",
          projectId,
          textContent: await file.text(),
          filename: file.name,
          mimeType: semanticTextMime(file.name, file.type),
        });
      } else {
        await create({
          type,
          projectId,
          content: await file.arrayBuffer(),
          filename: file.name,
          mimeType: file.type || null,
        });
      }
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    })().catch(() => undefined);
  };

  const error =
    localError ??
    (createInput.error
      ? runtime.researchAdapter.toPublicApplicationError(createInput.error)
          .safeMessage
      : null);

  return (
    <div className="research-input-panel">
      <Tabs defaultValue="text">
        <TabsList aria-label="新增研究输入类型">
          <TabsTrigger value="text">文本</TabsTrigger>
          <TabsTrigger value="url">网址</TabsTrigger>
          <TabsTrigger value="file">文件</TabsTrigger>
        </TabsList>
        <TabsContent value="text">
          <form onSubmit={submitText}>
            <Field>
              <FieldLabel htmlFor="research-input-text">内容</FieldLabel>
              <Textarea
                id="research-input-text"
                value={textContent}
                onChange={(event) => setTextContent(event.target.value)}
                placeholder="粘贴研究材料或 Markdown"
                required
              />
            </Field>
            <div className="research-input-panel__row">
              <Field>
                <FieldLabel htmlFor="research-input-text-format">
                  语义
                </FieldLabel>
                <Select
                  value={textFormat}
                  onValueChange={(value) =>
                    setTextFormat(value === "markdown" ? "markdown" : "plain")
                  }
                >
                  <SelectTrigger id="research-input-text-format">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="plain">纯文本</SelectItem>
                    <SelectItem value="markdown">Markdown</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="research-input-text-name">
                  文件名
                </FieldLabel>
                <Input
                  id="research-input-text-name"
                  value={textFilename}
                  onChange={(event) => setTextFilename(event.target.value)}
                  placeholder={
                    textFormat === "markdown" ? "notes.md" : "notes.txt"
                  }
                />
              </Field>
            </div>
            <Button
              type="submit"
              size="small"
              disabled={createInput.isPending || !textContent.trim()}
            >
              <Plus data-icon="inline-start" aria-hidden="true" />
              添加文本
            </Button>
          </form>
        </TabsContent>
        <TabsContent value="url">
          <form onSubmit={submitUrl}>
            <Field>
              <FieldLabel htmlFor="research-input-url">网址</FieldLabel>
              <Input
                id="research-input-url"
                type="url"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://example.org/data"
                required
              />
              <FieldDescription>
                服务端按安全策略抓取并固定来源快照。
              </FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="research-input-url-name">
                显示名称
              </FieldLabel>
              <Input
                id="research-input-url-name"
                value={urlFilename}
                onChange={(event) => setUrlFilename(event.target.value)}
                placeholder="可选"
              />
            </Field>
            <Button
              type="submit"
              size="small"
              disabled={createInput.isPending || !url.trim()}
            >
              <Plus data-icon="inline-start" aria-hidden="true" />
              添加网址
            </Button>
          </form>
        </TabsContent>
        <TabsContent value="file">
          <form onSubmit={submitFile}>
            <Field>
              <FieldLabel htmlFor="research-input-file">选择文件</FieldLabel>
              <Input
                ref={fileInputRef}
                id="research-input-file"
                type="file"
                accept={FILE_ACCEPT}
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
              <FieldDescription>
                PDF、CSV、XLSX、Parquet、JSON、图像、FITS；图像数据集 ZIP
                根目录需含 labels.json；Markdown 按 text + MIME 入站。
              </FieldDescription>
            </Field>
            {file ? (
              <p className="research-input-panel__selection">
                {file.name} · {formatBytes(file.size)} ·{" "}
                {file.type || "MIME 未提供"}
              </p>
            ) : null}
            <Button
              type="submit"
              size="small"
              disabled={createInput.isPending || file === null}
            >
              <Plus data-icon="inline-start" aria-hidden="true" />
              上传文件
            </Button>
          </form>
        </TabsContent>
      </Tabs>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <section
        className="research-input-panel__owned"
        aria-labelledby="research-input-owned-title"
      >
        <div className="research-input-panel__heading">
          <h4 id="research-input-owned-title">本 Project 输入</h4>
          <Badge variant="outline">{inputs.data?.length ?? 0}</Badge>
        </div>
        {inputs.isPending ? (
          <div aria-busy="true" aria-label="正在读取研究输入">
            <Skeleton />
            <Skeleton />
          </div>
        ) : inputs.isError ? (
          <Alert variant="destructive">
            <AlertDescription>
              {
                runtime.researchAdapter.toPublicApplicationError(inputs.error)
                  .safeMessage
              }
            </AlertDescription>
            <Button
              type="button"
              variant="ghost"
              size="small"
              onClick={() => void inputs.refetch()}
            >
              <RotateCcw data-icon="inline-start" aria-hidden="true" />
              重试
            </Button>
          </Alert>
        ) : (
          <ResearchInputList inputs={inputs.data} />
        )}
      </section>
    </div>
  );
}
