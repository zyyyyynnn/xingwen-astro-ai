import { Link } from "@tanstack/react-router";

import { ResearchShell } from "../components/research-shell";

export function EntryPage() {
  return (
    <ResearchShell
      status="准备就绪"
      atlas={<p className="region-placeholder">选择引导或已有研究上下文。</p>}
      observatory={
        <p className="region-placeholder">选择产物后显示来源与证据。</p>
      }
      console={<Link to="/tour">开始引导</Link>}
    >
      <section className="route-content" aria-labelledby="route-title">
        <h1 id="route-title">科研工作台入口</h1>
        <p>从已冻结的研究场景开始，或通过 URL 提供已有研究上下文。</p>
        <div className="action-row">
          <Link className="text-link" to="/tour">
            打开引导
          </Link>
          <Link className="text-link" to="/workspace">
            打开工作区
          </Link>
        </div>
      </section>
    </ResearchShell>
  );
}
