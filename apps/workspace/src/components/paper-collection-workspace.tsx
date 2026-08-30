import { useMutation, useQuery } from "@tanstack/react-query";
import { safeExternalUrl, type DomainEntityId } from "@xingwen/domain";
import type {
  ArtifactVersionMetadataViewModel,
  PaperAcquisitionReviewViewModel,
} from "@xingwen/research-adapter";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
  Alert,
  AlertDescription,
  Badge,
  Button,
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
  Input,
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
  ScrollArea,
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
  ToggleGroup,
  ToggleGroupItem,
  buttonClassName,
} from "@xingwen/ui";
import { ExternalLink, FileSearch, FileText, Search } from "@xingwen/ui/icons";
import { useMemo, useState } from "react";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";

type CollectionFilter = "all" | "selected" | "candidate";
type PaperCandidate = PaperAcquisitionReviewViewModel["candidates"][number];

export interface PaperCollectionWorkspaceProps {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly version: ArtifactVersionMetadataViewModel;
  readonly review: PaperAcquisitionReviewViewModel;
}

function selectionReasonLabel(reason: string | null): string | null {
  if (!reason) return null;
  const publicReason = reason
    .replace(/\s+candidate\.[0-9a-f]+$/iu, "")
    .split(/\r?\n/u)
    .filter((line) => !/^candidate\s*:/iu.test(line.trim()))
    .join(" ")
    .trim();
  if (
    /^highest ranked representative within selection limit$/iu.test(
      publicReason,
    )
  ) {
    return "在当前检索口径与选择上限内，作为该文献身份的代表记录纳入。";
  }
  if (/^duplicate of higher-ranked candidate$/iu.test(publicReason)) {
    return "与排名更高的记录属于同一文献身份，保留用于重复记录核验。";
  }
  if (
    /^selection limit reached after deterministic ranking$/iu.test(publicReason)
  ) {
    return "已达到当前选择上限，保留为后续审查的备选记录。";
  }
  return publicReason;
}

function sourceLabel(sourceId: DomainEntityId): string {
  if (String(sourceId).toLocaleLowerCase().includes("crossref")) {
    return "Crossref";
  }
  return "文献元数据来源";
}

function conflictFieldLabel(field: string): string {
  const labels: Record<string, string> = {
    authors: "作者",
    title: "标题",
    year: "年份",
    doi: "DOI",
    arxiv_id: "arXiv",
  };
  return labels[field] ?? "书目信息";
}

function syntheticReviewLabel(note: string | null): string | null {
  if (!note) return null;
  if (/duplicate/iu.test(note)) return "重复记录演示";
  if (/uncertain/iu.test(note)) return "身份冲突演示";
  if (/off-topic|unrelated/iu.test(note)) return "低相关记录演示";
  return "演示审查记录";
}

function candidateStatus(candidate: PaperCandidate): {
  readonly label: string;
  readonly variant: "default" | "secondary" | "outline";
} {
  if (candidate.selection.kind === "selected") {
    return { label: "已选", variant: "default" };
  }
  if (
    candidate.conflicts.some(
      (item) => item.classification === "uncertain_match",
    )
  ) {
    return { label: "身份待核", variant: "outline" };
  }
  return { label: "备选", variant: "secondary" };
}

export function PaperCollectionWorkspace({
  runtime,
  projectId,
  version,
  review,
}: PaperCollectionWorkspaceProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [filterMode, setFilterMode] = useState<CollectionFilter>("all");
  const [selectedInputId, setSelectedInputId] = useState<DomainEntityId | null>(
    null,
  );
  const [targetCandidateId, setTargetCandidateId] = useState<string | null>(
    null,
  );

  const inputs = useQuery(
    runtime.application.queries.researchInputs(projectId),
  );
  const documentInputs = useMemo(
    () =>
      (inputs.data ?? []).filter(
        (input) =>
          input.type === "pdf" ||
          input.type === "image" ||
          input.mimeType === "application/pdf" ||
          ["image/jpeg", "image/png", "image/tiff", "image/webp"].includes(
            input.mimeType ?? "",
          ),
      ),
    [inputs.data],
  );

  const binding = useMutation({
    mutationFn: async ({
      candidateId,
      canonicalPaperId,
      evidenceUrl,
      researchInputId,
    }: {
      candidateId: DomainEntityId;
      canonicalPaperId: DomainEntityId;
      evidenceUrl: string;
      researchInputId: DomainEntityId;
    }) => {
      const input = documentInputs.find((item) => item.id === researchInputId);
      if (!input || !evidenceUrl) {
        throw new Error("缺少可绑定的科研文档或论文来源地址");
      }
      await runtime.repositories.paperAcquisition.bindResearchInput({
        artifactVersionId: version.id,
        candidateId,
        canonicalPaperId,
        researchInputId: input.id,
        researchInputContentHash: input.contentHash,
        evidenceUrl,
        idempotencyKey: globalThis.crypto.randomUUID(),
      });
    },
  });

  const allCandidates = review.candidates;
  const selectedCandidates = useMemo(
    () =>
      allCandidates.filter(
        (candidate) => candidate.selection.kind === "selected",
      ),
    [allCandidates],
  );
  const filteredCandidates = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLocaleLowerCase();
    return allCandidates.filter((candidate) => {
      if (
        filterMode === "selected" &&
        candidate.selection.kind !== "selected"
      ) {
        return false;
      }
      if (
        filterMode === "candidate" &&
        candidate.selection.kind === "selected"
      ) {
        return false;
      }
      if (normalizedQuery.length === 0) return true;
      return (
        candidate.title.toLocaleLowerCase().includes(normalizedQuery) ||
        candidate.authors.some((author) =>
          author.toLocaleLowerCase().includes(normalizedQuery),
        ) ||
        String(candidate.year ?? "").includes(normalizedQuery) ||
        (candidate.doi?.toLocaleLowerCase().includes(normalizedQuery) ?? false)
      );
    });
  }, [allCandidates, filterMode, searchQuery]);
  const conflictCount = allCandidates.reduce(
    (total, candidate) => total + candidate.conflicts.length,
    0,
  );

  return (
    <section
      className="paper-collection-workspace"
      aria-labelledby="paper-collection-title"
    >
      <header className="paper-collection-workspace__header">
        <div>
          <p className="ui-text-label text-muted-foreground">文献检索审查</p>
          <h2 id="paper-collection-title">候选筛选与全文绑定</h2>
          <p>
            {review.query.yearFrom}–{review.query.yearTo} ·{" "}
            {review.query.sourceIds.map(sourceLabel).join("、")} ·{" "}
            {review.query.originalKeywords.join("、")}
          </p>
        </div>
        <div className="paper-collection-workspace__status">
          <Badge
            variant={
              review.acquisition.status === "completed"
                ? "secondary"
                : "outline"
            }
          >
            {review.acquisition.status === "completed"
              ? "检索完成"
              : "部分结果"}
          </Badge>
          <span>
            {review.sourceMode === "fixture" ? "演示数据" : "研究数据"}
          </span>
        </div>
      </header>

      <dl className="paper-collection-workspace__metrics">
        <div>
          <dt>候选</dt>
          <dd>{review.metrics.candidateCount}</dd>
        </div>
        <div>
          <dt>已选</dt>
          <dd>{review.metrics.selectedCount}</dd>
        </div>
        <div>
          <dt>重复记录</dt>
          <dd>{review.metrics.duplicateCandidateCount}</dd>
        </div>
        <div>
          <dt>字段冲突</dt>
          <dd>{conflictCount}</dd>
        </div>
      </dl>

      <div className="paper-collection-workspace__toolbar">
        <Field className="paper-collection-workspace__search">
          <FieldLabel htmlFor="paper-collection-search" className="sr-only">
            搜索论文集合
          </FieldLabel>
          <FieldContent>
            <div className="paper-collection-workspace__search-control">
              <Search aria-hidden="true" />
              <Input
                id="paper-collection-search"
                type="search"
                aria-label="搜索论文集合"
                placeholder="标题、作者、年份或 DOI"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </div>
          </FieldContent>
        </Field>
        <ToggleGroup
          type="single"
          variant="segmented"
          size="sm"
          value={filterMode}
          onValueChange={(value) => {
            if (value) setFilterMode(value as CollectionFilter);
          }}
          aria-label="筛选论文"
        >
          <ToggleGroupItem value="all">
            全部 {allCandidates.length}
          </ToggleGroupItem>
          <ToggleGroupItem value="selected">
            已选 {selectedCandidates.length}
          </ToggleGroupItem>
          <ToggleGroupItem value="candidate">
            其他 {allCandidates.length - selectedCandidates.length}
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      <ScrollArea className="paper-collection-workspace__list-scroll">
        {filteredCandidates.length > 0 ? (
          <ItemGroup
            className="paper-collection-workspace__list"
            aria-live="polite"
          >
            {filteredCandidates.map((candidate) => {
              const isSelected = candidate.selection.kind === "selected";
              const isTargetBinding =
                targetCandidateId === candidate.candidateId;
              const status = candidateStatus(candidate);
              const externalUrl = safeExternalUrl(candidate.url);
              const reason = selectionReasonLabel(candidate.selection.reason);
              const syntheticLabel = syntheticReviewLabel(
                candidate.rawRecord.syntheticNote,
              );
              const duplicateLabel =
                candidate.duplicateGroup.candidateIds.length > 1
                  ? "同一文献记录"
                  : syntheticLabel;
              return (
                <Item
                  key={candidate.candidateId}
                  className="paper-collection-workspace__row"
                  size="default"
                >
                  <ItemContent>
                    <div className="paper-collection-workspace__row-meta">
                      <Badge variant={status.variant}>{status.label}</Badge>
                      <span>排名 {candidate.stableRank}</span>
                      {duplicateLabel ? <span>{duplicateLabel}</span> : null}
                    </div>
                    <ItemTitle>{candidate.title}</ItemTitle>
                    <ItemDescription>
                      {candidate.authors.join("，") || "作者信息不可用"}
                      {candidate.year ? ` · ${candidate.year}` : ""}
                    </ItemDescription>
                    <p className="paper-collection-workspace__identity">
                      {candidate.doi
                        ? `DOI ${candidate.doi}`
                        : candidate.arxivId
                          ? `arXiv ${candidate.arxivId}`
                          : "无公开持久标识"}
                    </p>
                    {reason ? (
                      <p className="paper-collection-workspace__reason">
                        {reason}
                      </p>
                    ) : null}

                    <Accordion
                      type="single"
                      collapsible
                      className="paper-collection-workspace__details"
                    >
                      <AccordionItem value="details">
                        <AccordionTrigger>书目核验与来源</AccordionTrigger>
                        <AccordionContent>
                          <dl>
                            <div>
                              <dt>来源</dt>
                              <dd>
                                {sourceLabel(candidate.sourceSnapshot.sourceId)}
                              </dd>
                            </div>
                            <div>
                              <dt>身份依据</dt>
                              <dd>
                                {candidate.doi
                                  ? "DOI 精确身份"
                                  : candidate.arxivId
                                    ? "arXiv 身份"
                                    : "标题、年份与作者组合"}
                              </dd>
                            </div>
                            <div>
                              <dt>重复核验</dt>
                              <dd>
                                {candidate.duplicateGroup.candidateIds.length >
                                1
                                  ? `${candidate.duplicateGroup.candidateIds.length} 条记录属于同一文献身份`
                                  : "未发现同身份重复记录"}
                              </dd>
                            </div>
                          </dl>
                          {candidate.conflicts.length > 0 ? (
                            <ul>
                              {candidate.conflicts.map((conflict, index) => (
                                <li
                                  key={`${candidate.candidateId}:conflict:${index}`}
                                >
                                  {conflictFieldLabel(conflict.field)}字段
                                  {conflict.classification === "uncertain_match"
                                    ? "存在不确定匹配"
                                    : "存在来源冲突"}
                                </li>
                              ))}
                            </ul>
                          ) : null}
                        </AccordionContent>
                      </AccordionItem>
                    </Accordion>

                    {isTargetBinding && isSelected ? (
                      <div className="paper-collection-workspace__binding">
                        <Field>
                          <FieldLabel>绑定已上传全文</FieldLabel>
                          <FieldDescription>
                            绑定后可通过修订研究生成页码与段落级证据定位。
                          </FieldDescription>
                          <FieldContent>
                            {documentInputs.length > 0 ? (
                              <div className="paper-collection-workspace__binding-controls">
                                <Select
                                  value={selectedInputId ?? ""}
                                  onValueChange={(value) =>
                                    setSelectedInputId(value as DomainEntityId)
                                  }
                                >
                                  <SelectTrigger aria-label="选择科研文档">
                                    <SelectValue placeholder="选择已上传 PDF" />
                                  </SelectTrigger>
                                  <SelectContent>
                                    <SelectGroup>
                                      {documentInputs.map((document) => (
                                        <SelectItem
                                          key={document.id}
                                          value={document.id}
                                        >
                                          {document.filename ?? "未命名文档"}
                                        </SelectItem>
                                      ))}
                                    </SelectGroup>
                                  </SelectContent>
                                </Select>
                                <Button
                                  size="small"
                                  disabled={
                                    selectedInputId === null ||
                                    binding.isPending
                                  }
                                  onClick={() => {
                                    if (selectedInputId && externalUrl) {
                                      binding.mutate({
                                        candidateId: candidate.candidateId,
                                        canonicalPaperId:
                                          candidate.canonicalPaperId,
                                        evidenceUrl: externalUrl,
                                        researchInputId: selectedInputId,
                                      });
                                    }
                                  }}
                                >
                                  {binding.isPending
                                    ? "正在绑定…"
                                    : "确认绑定全文"}
                                </Button>
                              </div>
                            ) : (
                              <p>当前项目尚未上传受支持的 PDF。</p>
                            )}
                          </FieldContent>
                        </Field>
                        {binding.isSuccess ? (
                          <p role="status">全文绑定已建立。</p>
                        ) : null}
                        {binding.isError ? (
                          <Alert variant="destructive">
                            <AlertDescription>
                              {
                                runtime.researchAdapter.toPublicApplicationError(
                                  binding.error,
                                ).safeMessage
                              }
                            </AlertDescription>
                          </Alert>
                        ) : null}
                      </div>
                    ) : null}
                  </ItemContent>

                  <ItemActions className="paper-collection-workspace__actions">
                    {externalUrl ? (
                      <a
                        href={externalUrl}
                        target="_blank"
                        rel="noreferrer"
                        className={buttonClassName({
                          variant: "secondary",
                          size: "small",
                        })}
                      >
                        打开来源
                        <ExternalLink
                          data-icon="inline-end"
                          aria-hidden="true"
                        />
                      </a>
                    ) : (
                      <span className="ui-text-label text-muted-foreground">
                        无安全外链
                      </span>
                    )}
                    {isSelected ? (
                      <Button
                        variant="ghost"
                        size="small"
                        aria-expanded={isTargetBinding}
                        onClick={() =>
                          setTargetCandidateId(
                            isTargetBinding ? null : candidate.candidateId,
                          )
                        }
                      >
                        <FileText data-icon="inline-start" aria-hidden="true" />
                        {isTargetBinding ? "收起全文绑定" : "绑定全文"}
                      </Button>
                    ) : null}
                  </ItemActions>
                </Item>
              );
            })}
          </ItemGroup>
        ) : (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <FileSearch aria-hidden="true" />
              </EmptyMedia>
              <EmptyTitle>没有匹配的论文</EmptyTitle>
              <EmptyDescription>
                调整搜索词或切换筛选范围后重试。
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}
      </ScrollArea>
    </section>
  );
}
