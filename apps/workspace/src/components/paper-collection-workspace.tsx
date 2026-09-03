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
  Badge,
  Button,
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Field,
  FieldContent,
  FieldLabel,
  Input,
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemTitle,
  ScrollArea,
  ToggleGroup,
  ToggleGroupItem,
  buttonClassName,
} from "@xingwen/ui";
import { ExternalLink, FileSearch, FileText, Search } from "@xingwen/ui/icons";
import { useMemo, useState } from "react";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";
import { PaperFullTextForm } from "./paper-full-text-form";

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
  const [targetCandidateId, setTargetCandidateId] = useState<string | null>(
    null,
  );

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
    <section className="paper-collection-workspace" aria-label="文献候选审查">
      <header className="paper-collection-workspace__header">
        <div>
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
          <Badge variant="outline">
            {review.sourceMode === "fixture" ? "演示数据" : "研究数据"}
          </Badge>
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
            role="list"
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
                  role="listitem"
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
                      <PaperFullTextForm
                        key={`${version.id}:${candidate.candidateId}`}
                        runtime={runtime}
                        projectId={projectId}
                        artifactVersionId={version.id}
                        candidateId={candidate.candidateId}
                        canonicalPaperId={candidate.canonicalPaperId}
                        sourceUrl={externalUrl}
                        isLive={review.sourceMode === "live"}
                      />
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
                      <span className="ui-text-label paper-collection-workspace__unavailable">
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
                        {isTargetBinding ? "收起全文" : "关联全文"}
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
