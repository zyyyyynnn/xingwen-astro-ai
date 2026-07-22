import { useEffect, useState } from "react";
import { useRouteContext } from "@tanstack/react-router";
import type { RepositorySet } from "@xingwen/data-access";

type PublicShare = NonNullable<
  Awaited<ReturnType<RepositorySet["shares"]["getPublic"]>>
>;

export interface SharePageProps {
  readonly shareToken: string;
}

type PublicShareState =
  | { readonly status: "loading" }
  | { readonly status: "unavailable" }
  | { readonly status: "error" }
  | { readonly status: "ready"; readonly share: PublicShare };

export function SharePage({ shareToken }: SharePageProps) {
  const runtime = useRouteContext({ from: "/share/$shareToken" });
  const [state, setState] = useState<PublicShareState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void runtime.repositories.shares.getPublic(shareToken).then(
      (share) => {
        if (cancelled) return;
        setState(
          share ? { status: "ready", share } : { status: "unavailable" },
        );
      },
      () => {
        if (!cancelled) setState({ status: "error" });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt, runtime.repositories.shares, shareToken]);

  if (state.status === "loading") {
    return (
      <main className="public-share-page" aria-busy="true" aria-live="polite">
        <p>正在读取共享结果。</p>
      </main>
    );
  }

  if (state.status === "unavailable") {
    return (
      <main className="public-share-page">
        <h1>共享结果不可用</h1>
        <p>该结果可能已撤销或过期。</p>
      </main>
    );
  }

  if (state.status === "error") {
    return (
      <main className="public-share-page" role="alert">
        <h1>无法读取共享结果</h1>
        <p>请稍后重试。</p>
        <button
          type="button"
          onClick={() => setAttempt((current) => current + 1)}
        >
          重新读取共享结果
        </button>
      </main>
    );
  }

  const { share } = state;
  return (
    <main className="public-share-page" aria-labelledby="share-title">
      <p className="region-label">只读共享结果</p>
      <h1 id="share-title">{share.title}</h1>
      <p>
        创建于 {share.createdAt}，到期于 {share.expiresAt}
      </p>
      <section aria-labelledby="shared-version-title">
        <h2 id="shared-version-title">ArtifactVersion</h2>
        <ul className="share-list">
          {share.artifactVersions.map((version) => (
            <li key={version.id}>
              <span>{version.id}</span>
              <span>v{version.versionNumber}</span>
              <span>{version.sourceMode}</span>
              <span>{version.contentHash}</span>
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="shared-evidence-title">
        <h2 id="shared-evidence-title">Evidence</h2>
        <ul className="share-list">
          {share.evidence.map((evidence) => (
            <li key={evidence.id}>
              <span>{evidence.id}</span>
              <span>{evidence.artifactVersionId}</span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
