import { useEffect, useMemo, useState } from "react";
import { useRouteContext } from "@tanstack/react-router";
import type {
  DomainEntityId,
  PublicEvidence,
  PublicShareSnapshot,
} from "@xingwen/domain";
import { Button, Link, Spinner } from "@xingwen/ui";
import { ExternalLink, Share2 } from "@xingwen/ui/icons";

import { resolveArtifactRenderer } from "./presentation/artifact-renderer-registry";

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

function publicSourceUrl(evidence: PublicEvidence): string | null {
  const value =
    evidence.source.requestMetadata.source_url ??
    evidence.source.requestMetadata.url ??
    evidence.source.requestMetadata.original_url ??
    evidence.source.requestMetadata.landing_url;
  if (typeof value !== "string") return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" || parsed.protocol === "http:"
      ? parsed.toString()
      : null;
  } catch {
    return null;
  }
}

function publicValue(value: PublicEvidence["quoteOrValue"]): string {
  if (value === null) return "公开副本未提供摘录";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "公开副本未提供可读摘录";
}

const LOCATOR_LABELS: Readonly<Record<string, string>> = {
  page: "页码",
  paragraph: "段落",
  section: "章节",
  field: "字段",
  range: "范围",
  row_key: "记录",
};

const PUBLIC_SOURCE_TYPE_LABELS: Readonly<Record<string, string>> = {
  benchmark: "基准数据",
  catalog: "星表",
  database: "数据库",
  fixture: "演示数据",
  gaia_tap: "Gaia 星表",
  paper: "论文",
  paper_metadata: "论文元数据",
  research_input: "研究资料",
  research_input_upload: "用户上传",
  text: "用户输入",
  upload: "用户上传",
  url_fetch: "网页来源",
};

function publicSourceTypeLabel(sourceType: string): string {
  return PUBLIC_SOURCE_TYPE_LABELS[sourceType] ?? "公开来源";
}

function PublicEvidenceInspector({
  evidence,
  number,
  onClose,
}: {
  readonly evidence: PublicEvidence;
  readonly number: number;
  readonly onClose: () => void;
}) {
  const locatorFacts = Object.entries(evidence.locator).flatMap(
    ([key, value]) => {
      const label = LOCATOR_LABELS[key];
      if (!label || value === null || typeof value === "object") return [];
      return [{ label, value: String(value) }];
    },
  );
  const sourceUrl = publicSourceUrl(evidence);
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
      <blockquote>{publicValue(evidence.quoteOrValue)}</blockquote>
      {locatorFacts.length > 0 ? (
        <dl className="public-evidence__facts">
          {locatorFacts.map((fact) => (
            <div key={fact.label}>
              <dt>{fact.label}</dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      <dl className="public-evidence__facts">
        <div>
          <dt>来源类型</dt>
          <dd>{publicSourceTypeLabel(evidence.source.sourceType)}</dd>
        </div>
        <div>
          <dt>获取时间</dt>
          <dd>{formatDate(evidence.source.retrievedAt)}</dd>
        </div>
        <div>
          <dt>使用说明</dt>
          <dd>{evidence.source.licenseNote}</dd>
        </div>
      </dl>
      {sourceUrl ? (
        <Link href={sourceUrl} target="_blank" rel="noopener noreferrer">
          打开原始来源
          <ExternalLink aria-hidden="true" />
        </Link>
      ) : null}
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
      <p className="public-share-page__brand">星文智析 · 只读共享</p>
      <h1>共享结果当前不可用</h1>
      <p>该链接可能无效、已撤销或已过期。</p>
      {inFlight ? (
        <div className="route-loading" role="status">
          <Spinner aria-hidden="true" />
          <span>正在载入共享结果</span>
        </div>
      ) : null}
      <div className="action-row">
        <Button variant="secondary" onClick={onRetry} disabled={inFlight}>
          重试
        </Button>
        <Link href="/workspace">返回工作台</Link>
      </div>
    </main>
  );
}

export function PublicShareView({
  snapshot,
}: {
  readonly snapshot: PublicShareSnapshot;
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

  const copyShareLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopyStatus("链接已复制");
    } catch {
      setCopyStatus("浏览器未允许复制，请从地址栏复制链接");
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
          <Button variant="secondary" onClick={() => void copyShareLink()}>
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
            <renderer.PublicRenderer
              version={selectedVersion}
              onSelectEvidence={setSelectedEvidenceId}
            />
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
    return <PublicShareView snapshot={state.snapshot} />;
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
