import { BrandMark } from "@xingwen/ui";

/**
 * Minimal /workspace host after the legacy Workspace product layer retired
 * (A-20). Renders the brand mark, a skip link to main content, and a stable
 * desktop-first title. It does not mount any research UI.
 */
export function WorkspaceHost() {
  return (
    <div className="workspace-host">
      <a className="skip-link" href="#main-content">
        跳到主要内容
      </a>
      <header className="workspace-host__brand">
        <BrandMark />
      </header>
      <main id="main-content" tabIndex={-1} className="workspace-host__main">
        <h1>研究工作台</h1>
        <section className="workspace-host__narrow" aria-label="桌面设备提示">
          <p className="workspace-host__narrow-title">请使用桌面设备</p>
          <p>研究工作台需要更宽的浏览器窗口。</p>
        </section>
      </main>
    </div>
  );
}
