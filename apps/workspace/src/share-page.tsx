import { useEffect, useMemo, useState } from "react";
import { useRouteContext } from "@tanstack/react-router";
import type {
  ArtifactExportDownload,
  DomainEntityId,
  PublicShareSnapshot,
} from "@xingwen/domain";
import {
  Button,
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Link,
  Spinner,
  buttonClassName,
} from "@xingwen/ui";
import { CircleSlash2, Download, Quote, Share2 } from "@xingwen/ui/icons";

import { ArtifactPresentationContent } from "./components/scientific-presentation";
import {
  buildEvidencePresentation,
  EvidencePresentationContent,
} from "./components/evidence-presentation";
import {
  resolveArtifactRenderer,
  UnsupportedArtifactPresentation,
} from "./presentation/artifact-renderer-registry";
import { downloadBytes } from "./presentation/browser-download";

export interface SharePageProps {
  readonly shareToken: string;
}

type ShareLoadState =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly snapshot: PublicShareSnapshot }
  | { readonly status: "unavailable" };

function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function PublicEvidenceInspector({
  evidence,
  number,
  onClose,
}: {
  readonly evidence: PublicShareSnapshot["evidence"][number];
  readonly number: number;
  readonly onClose: () => void;
}) {
  return (
    <aside className="public-evidence" aria-labelledby="public-evidence-title">
      <div className="public-evidence__header">
        <div>
          <p>核验材料</p>
          <h2 id="public-evidence-title">证据 {number}</h2>
        </div>
        <Button size="small" variant="ghost" onClick={onClose}>
          关闭
        </Button>
      </div>
      <EvidencePresentationContent
        presentation={buildEvidencePresentation(evidence)}
      />
    </aside>
  );
}

function PublicShareUnavailable({
  inFlight,
  onRetry,
}: {
  readonly inFlight: boolean;
  readonly onRetry: () => void;
}) {
  return (
    <main
      className="public-share-page public-share-page--boundary"
      aria-live="polite"
    >
      <Empty className="public-share-boundary__empty border-0 bg-transparent">
        <EmptyHeader>
          <p className="public-share-page__brand">星文智析 · 只读共享</p>
          <EmptyMedia variant="icon">
            {inFlight ? (
              <Spinner aria-hidden="true" />
            ) : (
              <CircleSlash2 aria-hidden="true" />
            )}
          </EmptyMedia>
          <EmptyTitle>
            {inFlight ? "正在载入共享结果" : "共享结果当前不可用"}
          </EmptyTitle>
          <EmptyDescription>
            {inFlight
              ? "正在核验只读链接及其冻结版本。"
              : "该链接可能无效、已撤销或已过期。原研究结果不会因此受到影响。"}
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Button variant="primary" onClick={onRetry} disabled={inFlight}>
              重试
            </Button>
            <a
              href="/workspace"
              className={buttonClassName({ variant: "secondary" })}
            >
              返回工作台
            </a>
          </div>
        </EmptyContent>
      </Empty>
    </main>
  );
}

export function PublicShareView({
  snapshot,
  onDownloadDatasetCsv = null,
}: {
  readonly snapshot: PublicShareSnapshot;
  readonly onDownloadDatasetCsv?:
    | ((artifactVersionId: DomainEntityId) => Promise<ArtifactExportDownload>)
    | null;
}) {
  const orderedVersions = useMemo(
    () =>
      [...snapshot.artifactVersions].sort((left, right) => {
        const leftPriority =
          resolveArtifactRenderer(left.kind)?.displayPriority ?? 999;
        const rightPriority =
          resolveArtifactRenderer(right.kind)?.displayPriority ?? 999;
        return leftPriority - rightPriority;
      }),
    [snapshot.artifactVersions],
  );
  const [selectedVersionId, setSelectedVersionId] =
    useState<DomainEntityId | null>(orderedVersions[0]?.id ?? null);
  const [selectedEvidenceId, setSelectedEvidenceId] =
    useState<DomainEntityId | null>(null);
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const [downloadState, setDownloadState] = useState<
    "idle" | "pending" | "error"
  >("idle");
  const evidenceOrdinals = useMemo(
    () =>
      new Map(
        snapshot.evidence.map((evidence, index) => [evidence.id, index + 1]),
      ),
    [snapshot.evidence],
  );
  const selectedVersion =
    orderedVersions.find((version) => version.id === selectedVersionId) ??
    orderedVersions[0] ??
    null;
  const selectedEvidence = snapshot.evidence.find(
    (evidence) => evidence.id === selectedEvidenceId,
  );
  const selectedEvidenceNumber = selectedEvidence
    ? snapshot.evidence.indexOf(selectedEvidence) + 1
    : 0;
  const renderer = selectedVersion
    ? resolveArtifactRenderer(selectedVersion.kind)
    : null;
  const showSelectedResultHeader =
    orderedVersions.length > 1 || snapshot.title !== selectedVersion?.title;

  const copyShareLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopyStatus("链接已复制");
    } catch {
      setCopyStatus("浏览器未允许复制，请从地址栏复制链接");
    }
  };
  const downloadDatasetCsv = async () => {
    if (!selectedVersion || !onDownloadDatasetCsv) return;
    setDownloadState("pending");
    try {
      downloadBytes(await onDownloadDatasetCsv(selectedVersion.id));
      setDownloadState("idle");
    } catch {
      setDownloadState("error");
    }
  };

  return (
    <main className="public-share-page">
      <header className="public-share-hero">
        <div className="public-share-hero__topline">
          <p className="public-share-page__brand">星文智析 · 只读共享</p>
          <Link href="/workspace">打开工作台</Link>
        </div>
        <div className="public-share-hero__title-row">
          <div>
            <h1>{snapshot.title}</h1>
            <p>
              创建于 {formatDate(snapshot.createdAt)} · 有效至{" "}
              {formatDate(snapshot.expiresAt)}
            </p>
          </div>
          <Button
            variant="secondary"
            className="shrink-0 whitespace-nowrap"
            onClick={() => void copyShareLink()}
          >
            <Share2 aria-hidden="true" />
            复制链接
          </Button>
        </div>
        {copyStatus ? (
          <p className="public-share-hero__copy-status" role="status">
            {copyStatus}
          </p>
        ) : null}
        <p className="public-share-hero__notice">
          此页面是创建分享时冻结的公开副本，不会随原研究项目的后续修改而变化。
        </p>
      </header>

      {selectedVersion && renderer ? (
        <div
          className="public-share-layout"
          data-has-navigation={orderedVersions.length > 1}
          data-has-evidence={selectedEvidence !== undefined}
        >
          {orderedVersions.length > 1 ? (
            <nav className="public-share-results" aria-label="共享结果">
              <p>共享内容</p>
              {orderedVersions.map((version) => (
                <Button
                  key={version.id}
                  variant="ghost"
                  aria-current={
                    version.id === selectedVersion.id ? "page" : undefined
                  }
                  onClick={() => {
                    setSelectedVersionId(version.id);
                    setSelectedEvidenceId(null);
                    setDownloadState("idle");
                  }}
                >
                  <span>{version.title}</span>
                  <small>
                    {resolveArtifactRenderer(version.kind)?.label ?? "研究结果"}
                  </small>
                </Button>
              ))}
            </nav>
          ) : null}
          <section className="public-share-result" aria-label="共享科研结果">
            {renderer.capability === "supported" &&
            selectedVersion.kind === "dataset" &&
            onDownloadDatasetCsv ? (
              <div
                className="public-share-result__header"
                data-mode={showSelectedResultHeader ? "actions" : "summary"}
              >
                {!showSelectedResultHeader ? (
                  <div>
                    <p>共享数据集</p>
                    <h2>数据概览</h2>
                  </div>
                ) : null}
                <div className="public-share-result__toolbar">
                  <Button
                    size="small"
                    variant="secondary"
                    disabled={downloadState === "pending"}
                    onClick={() => void downloadDatasetCsv()}
                  >
                    <Download data-icon="inline-start" aria-hidden="true" />
                    {downloadState === "pending" ? "正在下载" : "下载 CSV"}
                  </Button>
                  {downloadState === "error" ? (
                    <p role="alert">下载失败，请重试。</p>
                  ) : null}
                </div>
              </div>
            ) : null}
            {renderer.capability === "unsupported" ? (
              <UnsupportedArtifactPresentation descriptor={renderer} />
            ) : (
              <ArtifactPresentationContent
                title={selectedVersion.title}
                presentation={selectedVersion.presentation}
                surface="fullscreen"
                showHeader={showSelectedResultHeader}
                onSelectEvidence={setSelectedEvidenceId}
                evidenceOrdinal={(evidenceId) =>
                  evidenceOrdinals.get(evidenceId) ?? null
                }
              />
            )}
            {selectedVersion.evidenceIds.length > 0 ? (
              <section
                className="public-share-evidence-links"
                aria-label="公开证据"
              >
                <h2>核验证据</h2>
                <div>
                  {selectedVersion.evidenceIds.map((evidenceId) => {
                    const evidence = snapshot.evidence.find(
                      (item) => item.id === evidenceId,
                    );
                    if (!evidence) return null;
                    const number = snapshot.evidence.indexOf(evidence) + 1;
                    return (
                      <Button
                        key={evidenceId}
                        size="small"
                        variant="secondary"
                        onClick={() => setSelectedEvidenceId(evidenceId)}
                      >
                        <Quote data-icon="inline-start" aria-hidden="true" />
                        查看证据 {number}
                      </Button>
                    );
                  })}
                </div>
              </section>
            ) : null}
          </section>
          {selectedEvidence ? (
            <PublicEvidenceInspector
              evidence={selectedEvidence}
              number={selectedEvidenceNumber}
              onClose={() => setSelectedEvidenceId(null)}
            />
          ) : null}
        </div>
      ) : (
        <section className="public-share-result public-share-result--empty">
          <h2>共享内容为空</h2>
          <p>该公开副本没有可展示的科研结果。</p>
        </section>
      )}
    </main>
  );
}

/** Anonymous route: the token is only used as a read parameter and is never rendered. */
export function SharePage({ shareToken }: SharePageProps) {
  const runtime = useRouteContext({ from: "/share/$shareToken" });
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<ShareLoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    void runtime.repositories.shares.getPublic(shareToken).then(
      (snapshot) => {
        if (cancelled) return;
        setState(
          snapshot ? { status: "ready", snapshot } : { status: "unavailable" },
        );
      },
      () => {
        if (!cancelled) setState({ status: "unavailable" });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt, runtime.repositories.shares, shareToken]);

  if (state.status === "ready") {
    return (
      <PublicShareView
        snapshot={state.snapshot}
        onDownloadDatasetCsv={(artifactVersionId) =>
          runtime.repositories.shares.downloadPublicDatasetCsv(
            shareToken,
            artifactVersionId,
          )
        }
      />
    );
  }
  return (
    <PublicShareUnavailable
      inFlight={state.status === "loading"}
      onRetry={() => {
        setState({ status: "loading" });
        setAttempt((current) => current + 1);
      }}
    />
  );
}
