import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { DomainEntityId } from "@xingwen/domain";
import type { ResearchInputRef, ResearchInputType } from "@xingwen/data-access";
import { Button, Input } from "@xingwen/ui";
import {
  Check,
  FileText,
  Loader2,
  Paperclip,
  RotateCcw,
  X,
} from "@xingwen/ui/icons";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";

export type ResearchAttachmentStatus = "uploading" | "uploaded" | "failed";

export interface ResearchAttachmentItem {
  readonly id: string;
  readonly filename: string;
  readonly sizeBytes: number;
  readonly status: ResearchAttachmentStatus;
  readonly errorMessage: string | null;
  readonly removable: boolean;
}

interface AttachmentRecord extends ResearchAttachmentItem {
  readonly file: File;
  readonly input: ResearchInputRef | null;
  readonly boundTarget: string | null;
}

interface UseResearchAttachmentsOptions {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId | null;
  readonly draftId?: DomainEntityId | null;
  /** Active Run is intentionally not an attachment binding target. */
  readonly runId?: DomainEntityId | null;
  readonly ensureProject?: () => Promise<DomainEntityId>;
  readonly onProjectReady?: (projectId: DomainEntityId) => void;
}

const MIME_TO_TYPE: readonly [
  RegExp,
  Exclude<ResearchInputType, "url" | "text">,
][] = [
  [/^application\/pdf$/iu, "pdf"],
  [/^(?:text\/csv|application\/csv)$/iu, "csv"],
  [
    /^application\/vnd\.openxmlformats-officedocument\.spreadsheetml\.sheet$/iu,
    "xlsx",
  ],
  [/^application\/vnd\.apache\.parquet$/iu, "parquet"],
  [/^(?:application\/fits|image\/fits)$/iu, "fits"],
  [/^application\/json$/iu, "json"],
  // ZIP only enters the dedicated image_dataset validation boundary; arbitrary
  // archives are never advertised as supported.
  [/^application\/zip$/iu, "image_dataset"],
  [/^image\//iu, "image"],
];

export function inferInputType(
  file: File,
): Exclude<ResearchInputType, "url" | "text"> | null {
  const byMime = MIME_TO_TYPE.find(([pattern]) => pattern.test(file.type));
  if (byMime) return byMime[1];
  const extension = file.name.split(".").pop()?.toLowerCase();
  switch (extension) {
    case "pdf":
      return "pdf";
    case "csv":
      return "csv";
    case "xlsx":
      return "xlsx";
    case "parquet":
      return "parquet";
    case "fits":
    case "fit":
    case "fts":
      return "fits";
    case "json":
      return "json";
    case "zip":
      return "image_dataset";
    case "png":
    case "jpg":
    case "jpeg":
    case "gif":
    case "tif":
    case "tiff":
    case "webp":
      return "image";
    default:
      return null;
  }
}

function draftTargetKey(
  projectId: DomainEntityId | null,
  draftId: DomainEntityId | null | undefined,
): string | null {
  return projectId && draftId ? `draft:${String(draftId)}` : null;
}

function publicError(
  runtime: WorkspaceRuntimeBoundaries,
  error: unknown,
): string {
  return runtime.researchAdapter.toPublicApplicationError(error).safeMessage;
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function AttachmentStrip({
  items,
  onRetry,
  onRemove,
}: {
  readonly items: readonly ResearchAttachmentItem[];
  readonly onRetry: (id: string) => void;
  readonly onRemove: (id: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <div
      className="mb-2 flex flex-wrap gap-2"
      data-testid="research-attachment-strip"
      aria-label="已添加的研究资料"
    >
      {items.map((item) => (
        <div
          key={item.id}
          className="min-w-0 max-w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] px-2.5 py-1.5 text-xs text-[var(--color-ink-primary)]"
          data-status={item.status}
        >
          <div className="flex min-w-0 items-center gap-2">
            {item.status === "uploading" ? (
              <Loader2
                className="size-[var(--icon-size-sm)] shrink-0 animate-spin motion-reduce:animate-none"
                aria-hidden="true"
              />
            ) : item.status === "uploaded" ? (
              <Check
                className="size-[var(--icon-size-sm)] shrink-0"
                aria-hidden="true"
              />
            ) : (
              <FileText
                className="size-[var(--icon-size-sm)] shrink-0"
                aria-hidden="true"
              />
            )}
            <span className="min-w-0 truncate" title={item.filename}>
              {item.filename}
            </span>
            <span className="shrink-0 text-[var(--color-ink-secondary)]">
              {formatBytes(item.sizeBytes)}
            </span>
            {item.status === "failed" ? (
              <Button
                variant="ghost"
                size="small"
                onClick={() => onRetry(item.id)}
                className="h-6 gap-1 px-2"
              >
                <RotateCcw aria-hidden="true" />
                重试
              </Button>
            ) : null}
            {item.removable ? (
              <Button
                variant="ghost"
                size="icon-xsmall"
                aria-label={`移除 ${item.filename}`}
                disabled={item.status === "uploading"}
                onClick={() => onRemove(item.id)}
              >
                <X aria-hidden="true" />
              </Button>
            ) : null}
          </div>
          {item.errorMessage ? (
            <p
              className="mt-1 max-w-72 text-xs research-attachment__error"
              role="alert"
            >
              {item.errorMessage}
            </p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function useResearchAttachments({
  runtime,
  projectId,
  draftId = null,
  ensureProject,
  onProjectReady,
}: UseResearchAttachmentsOptions) {
  const [records, setRecords] = useState<readonly AttachmentRecord[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const localId = useRef(0);
  const createdProjectId = useRef<DomainEntityId | null>(projectId);
  const projectReadyNotified = useRef(projectId !== null);
  const bindingInputIds = useRef(new Set<DomainEntityId>());

  const uploadMutation = useMutation(
    runtime.application.mutations.researchInputCreate(),
  );
  const deleteMutation = useMutation(
    runtime.application.mutations.researchInputDelete(),
  );
  const bindDraftMutation = useMutation(
    runtime.application.mutations.researchInputBindToDraft(),
  );
  const existingInputs = useQuery({
    ...runtime.application.queries.researchInputs(projectId as DomainEntityId),
    enabled: projectId !== null,
  });

  useEffect(() => {
    if (projectId) createdProjectId.current = projectId;
  }, [projectId]);

  const markFailure = useCallback((recordId: string, message: string) => {
    setRecords((current) =>
      current.map((record) =>
        record.id === recordId
          ? { ...record, status: "failed", errorMessage: message }
          : record,
      ),
    );
  }, []);

  const bindRecordToDraft = useCallback(
    async (
      recordId: string,
      input: ResearchInputRef,
      effectiveProjectId: DomainEntityId,
      targetDraftId: DomainEntityId,
    ) => {
      try {
        const boundInput = await bindDraftMutation.mutateAsync({
          inputId: input.id,
          projectId: effectiveProjectId,
          draftId: targetDraftId,
        });
        setRecords((current) =>
          current.map((record) =>
            record.id === recordId
              ? {
                  ...record,
                  status: "uploaded",
                  input: boundInput,
                  boundTarget: draftTargetKey(
                    effectiveProjectId,
                    targetDraftId,
                  ),
                  removable: false,
                  errorMessage: null,
                }
              : record,
          ),
        );
      } catch (error) {
        markFailure(recordId, publicError(runtime, error));
      }
    },
    [bindDraftMutation, markFailure, runtime],
  );

  const upload = useCallback(
    async (recordId: string, file: File) => {
      const type = inferInputType(file);
      if (!type) {
        markFailure(
          recordId,
          "支持 PDF、CSV、XLSX、Parquet、FITS、JSON、图片，以及带 labels.json 的图像数据集 ZIP。",
        );
        return;
      }

      let effectiveProjectId = projectId ?? createdProjectId.current;
      try {
        if (!effectiveProjectId) {
          if (!ensureProject) throw new Error("请先创建研究项目。");
          effectiveProjectId = await ensureProject();
          createdProjectId.current = effectiveProjectId;
        }

        const input = await uploadMutation.mutateAsync({
          projectId: effectiveProjectId,
          type,
          file,
          filename: file.name,
          mimeType: file.type || "application/octet-stream",
          idempotencyKey: runtime.application.createResearchTurnActionId(),
        });

        setRecords((current) =>
          current.map((record) =>
            record.id === recordId
              ? {
                  ...record,
                  status: draftId ? "uploading" : "uploaded",
                  input,
                  boundTarget: null,
                  removable: draftId === null,
                  errorMessage: null,
                }
              : record,
          ),
        );

        if (draftId) {
          await bindRecordToDraft(recordId, input, effectiveProjectId, draftId);
        }

        if (
          projectId === null &&
          !projectReadyNotified.current &&
          onProjectReady
        ) {
          projectReadyNotified.current = true;
          onProjectReady(effectiveProjectId);
        }
      } catch (error) {
        markFailure(recordId, publicError(runtime, error));
      }
    },
    [
      bindRecordToDraft,
      draftId,
      ensureProject,
      markFailure,
      onProjectReady,
      projectId,
      runtime,
      uploadMutation,
    ],
  );

  const addFiles = useCallback(
    (files: readonly File[]) => {
      const next = files.filter((file) => file.size > 0);
      if (next.length === 0) return;
      const added = next.map((file) => {
        const id = `attachment-${String(++localId.current)}`;
        return {
          id,
          filename: file.name,
          sizeBytes: file.size,
          status: "uploading" as const,
          errorMessage: null,
          removable: true,
          file,
          input: null,
          boundTarget: null,
        } satisfies AttachmentRecord;
      });
      setRecords((current) => [...current, ...added]);
      for (const record of added) void upload(record.id, record.file);
    },
    [upload],
  );

  const retry = useCallback(
    (recordId: string) => {
      const record = records.find((item) => item.id === recordId);
      if (!record || record.status !== "failed") return;

      setRecords((current) =>
        current.map((item) =>
          item.id === recordId
            ? { ...item, status: "uploading", errorMessage: null }
            : item,
        ),
      );

      const effectiveProjectId = projectId ?? createdProjectId.current;
      if (record.input && draftId && effectiveProjectId) {
        void bindRecordToDraft(
          record.id,
          record.input,
          effectiveProjectId,
          draftId,
        );
        return;
      }
      void upload(record.id, record.file);
    },
    [bindRecordToDraft, draftId, projectId, records, upload],
  );

  const remove = useCallback(
    async (recordId: string) => {
      const record = records.find((item) => item.id === recordId);
      if (!record || record.status === "uploading" || !record.removable) return;
      if (!record.input) {
        setRecords((current) => current.filter((item) => item.id !== recordId));
        return;
      }
      try {
        await deleteMutation.mutateAsync({
          inputId: record.input.id,
          projectId: projectId ?? createdProjectId.current ?? undefined,
        });
        setRecords((current) => current.filter((item) => item.id !== recordId));
      } catch (error) {
        setRecords((current) =>
          current.map((item) =>
            item.id === recordId
              ? { ...item, errorMessage: publicError(runtime, error) }
              : item,
          ),
        );
      }
    },
    [deleteMutation, projectId, records, runtime],
  );

  // Inputs uploaded before a Draft exists may join that Draft once it becomes
  // the explicit authoring target. Active Run ids are intentionally ignored:
  // a frozen Run can only receive new formal material through Revision.
  useEffect(() => {
    const effectiveProjectId = projectId ?? createdProjectId.current;
    if (!effectiveProjectId || !draftId) return;

    for (const record of records) {
      if (
        record.status !== "uploaded" ||
        !record.input ||
        record.boundTarget ||
        bindingInputIds.current.has(record.input.id)
      ) {
        continue;
      }
      bindingInputIds.current.add(record.input.id);
      void bindRecordToDraft(
        record.id,
        record.input,
        effectiveProjectId,
        draftId,
      ).finally(() => {
        bindingInputIds.current.delete(
          record.input?.id ?? ("" as DomainEntityId),
        );
      });
    }
  }, [bindRecordToDraft, draftId, projectId, records]);

  const items = useMemo<readonly ResearchAttachmentItem[]>(() => {
    const localInputIds = new Set(
      records.flatMap((record) => (record.input ? [record.input.id] : [])),
    );
    const localItems = records.map(
      ({ id, filename, sizeBytes, status, errorMessage, removable }) => ({
        id,
        filename,
        sizeBytes,
        status,
        errorMessage,
        removable,
      }),
    );
    const persistedItems = (existingInputs.data ?? [])
      .filter((input) => !localInputIds.has(input.id))
      .map((input): ResearchAttachmentItem => ({
        id: `existing-${String(input.id)}`,
        filename: input.filename ?? "研究资料",
        sizeBytes: input.sizeBytes,
        status: "uploaded",
        errorMessage: null,
        removable: false,
      }));
    return [...localItems, ...persistedItems];
  }, [existingInputs.data, records]);

  const handleFilesSelected = useCallback(
    (files: readonly File[]) => addFiles(files),
    [addFiles],
  );
  const handlePasteFiles = handleFilesSelected;
  const handleDropFiles = useCallback(
    (files: readonly File[]) => {
      setDragActive(false);
      addFiles(files);
    },
    [addFiles],
  );
  const handleDragOver = useCallback(() => setDragActive(true), []);
  const handleDragLeave = useCallback(() => setDragActive(false), []);

  const attachmentAction: ReactNode = (
    <>
      <Input
        ref={inputRef}
        type="file"
        className="sr-only"
        accept=".pdf,.csv,.xlsx,.parquet,.fits,.fit,.fts,.json,.zip,image/*"
        multiple
        onChange={(event) => {
          handleFilesSelected(Array.from(event.target.files ?? []));
          event.target.value = "";
        }}
        aria-label="选择研究资料"
      />
      <Button
        variant="ghost"
        size="small"
        onClick={() => inputRef.current?.click()}
        aria-label="添加研究资料"
        className="gap-1 text-xs text-[var(--color-ink-secondary)]"
      >
        <Paperclip aria-hidden="true" />
        附件
      </Button>
    </>
  );

  const attachmentStrip: ReactNode = (
    <AttachmentStrip items={items} onRetry={retry} onRemove={remove} />
  );

  return {
    items,
    attachmentAction,
    attachmentStrip,
    dragActive,
    handleFilesSelected,
    handlePasteFiles,
    handleDropFiles,
    handleDragOver,
    handleDragLeave,
  };
}
