import { useMutation } from "@tanstack/react-query";
import type { DomainEntityId, UtcIsoTimestamp } from "@xingwen/domain";
import {
  Alert,
  AlertDescription,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Field,
  FieldContent,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  Input,
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@xingwen/ui";
import { useState } from "react";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";

const EXPIRY_OPTIONS = [
  { value: "7", label: "7 天" },
  { value: "30", label: "30 天" },
] as const;

function publicShareUrl(token: string): string {
  return new URL(
    `/share/${encodeURIComponent(token)}`,
    globalThis.location.origin,
  ).toString();
}

export function ArtifactShareDialog({
  runtime,
  projectId,
  artifactVersionId,
  artifactTitle,
  evidenceIds,
  open,
  onOpenChange,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifactVersionId: DomainEntityId;
  readonly artifactTitle: string;
  readonly evidenceIds: readonly DomainEntityId[];
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}) {
  const create = useMutation(runtime.application.mutations.shareCreate());
  const [expiryDays, setExpiryDays] = useState("7");
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">(
    "idle",
  );

  const setOpen = (nextOpen: boolean) => {
    if (!nextOpen) {
      create.reset();
      setShareUrl(null);
      setCopyState("idle");
    }
    onOpenChange(nextOpen);
  };

  const createShare = async () => {
    const expiresAt = new Date(
      Date.now() + Number(expiryDays) * 86_400_000,
    ).toISOString() as UtcIsoTimestamp;
    try {
      const created = await create.mutateAsync({
        projectId,
        request: {
          title: artifactTitle,
          artifactVersionIds: [artifactVersionId],
          evidenceIds: [...new Set(evidenceIds)],
          expiresAt,
          redactionPolicy: "redacted_public_snapshot",
        },
      });
      setShareUrl(publicShareUrl(created.shareToken));
    } catch {
      // The mutation owns the public error state rendered below.
    }
  };

  const copyLink = async () => {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>分享研究结果</DialogTitle>
          <DialogDescription>
            创建当前结果与关联证据的只读副本。
          </DialogDescription>
        </DialogHeader>

        {shareUrl ? (
          <Field>
            <FieldLabel htmlFor="artifact-share-url">分享链接</FieldLabel>
            <FieldContent className="flex-row gap-2">
              <Input
                id="artifact-share-url"
                value={shareUrl}
                readOnly
                onFocus={(event) => event.currentTarget.select()}
                className="min-w-0 flex-1"
              />
              <Button
                type="button"
                className="shrink-0 whitespace-nowrap"
                onClick={() => void copyLink()}
              >
                复制链接
              </Button>
            </FieldContent>
            {copyState === "copied" ? (
              <p className="ui-text-label text-muted-foreground" role="status">
                已复制
              </p>
            ) : copyState === "failed" ? (
              <p className="ui-text-label text-destructive" role="status">
                复制失败，请手动复制
              </p>
            ) : null}
          </Field>
        ) : (
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="artifact-share-expiry">有效期</FieldLabel>
              <Select value={expiryDays} onValueChange={setExpiryDays}>
                <SelectTrigger id="artifact-share-expiry">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {EXPIRY_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
              <FieldDescription>
                到期后链接自动失效，原研究与结果版本不受影响。
              </FieldDescription>
            </Field>
          </FieldGroup>
        )}

        {create.isError ? (
          <Alert variant="destructive">
            <AlertDescription>
              {
                runtime.researchAdapter.toPublicApplicationError(create.error)
                  .safeMessage
              }
            </AlertDescription>
          </Alert>
        ) : null}

        <DialogFooter>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setOpen(false)}
          >
            {shareUrl ? "完成" : "取消"}
          </Button>
          {!shareUrl ? (
            <Button
              type="button"
              disabled={create.isPending}
              onClick={() => void createShare()}
            >
              {create.isPending ? "正在创建" : "创建链接"}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
