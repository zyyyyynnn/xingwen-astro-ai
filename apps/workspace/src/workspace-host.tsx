import { OpenHandsWorkspaceRoot } from "../upstream/openhands/src/root";

/** Thin Xingwen route host around the source-adopted OpenHands product shell. */
export function WorkspaceHost() {
  return (
    <div className="workspace-host">
      <a className="skip-link" href="#main-content">
        跳到主要内容
      </a>
      <div className="workspace-host__desktop">
        <OpenHandsWorkspaceRoot />
      </div>
      <section className="workspace-host__narrow" aria-label="桌面设备提示">
        <h1>请使用桌面设备</h1>
        <p>研究工作台需要至少 1024 像素宽的浏览器窗口。</p>
      </section>
    </div>
  );
}
