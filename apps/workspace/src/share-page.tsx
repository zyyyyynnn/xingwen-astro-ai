import { useEffect, useState } from "react";
import { useRouteContext } from "@tanstack/react-router";
import { Button, Link, Spinner } from "@xingwen/ui";

export interface SharePageProps {
  readonly shareToken: string;
}

/**
 * Public share route with a fixed, non-disclosing failure boundary.
 *
 * Always renders the same safe boundary copy regardless of the repository
 * outcome: the token is used only as a read parameter, never rendered, and no
 * private session is created. The retry re-runs the public read and remains
 * on the same boundary.
 */
export function SharePage({ shareToken }: SharePageProps) {
  const runtime = useRouteContext({ from: "/share/$shareToken" });
  const [inFlight, setInFlight] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void runtime.repositories.shares.getPublic(shareToken).then(
      () => {
        if (!cancelled) setInFlight(false);
      },
      () => {
        if (!cancelled) setInFlight(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt, runtime.repositories.shares, shareToken]);

  const retry = () => {
    setInFlight(true);
    setAttempt((current) => current + 1);
  };

  return (
    <main className="public-share-page" aria-busy={inFlight} aria-live="polite">
      <h1>共享结果当前不可用</h1>
      <p>该链接可能无效、已撤销或已过期。</p>
      {inFlight ? <Spinner label="正在重新载入共享结果" /> : null}
      <div className="action-row">
        <Button variant="secondary" onClick={retry} disabled={inFlight}>
          重试
        </Button>
        <Link href="/">返回首页</Link>
      </div>
    </main>
  );
}
