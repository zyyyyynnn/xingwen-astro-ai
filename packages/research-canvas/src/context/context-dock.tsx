export function ContextDock({ 
  mode,
  onCloseDetail,
  onViewArtifact
}: { 
  mode: "summary" | "detail";
  onCloseDetail: () => void;
  onViewArtifact: () => void;
}) {
  return (
    <div className={`relative shrink-0 flex flex-col bg-[var(--color-surface)] border-l border-[var(--color-border)] transition-all duration-300 ${mode === "summary" ? 'w-[216px]' : 'w-[384px]'}`}>
      
      {mode === "summary" ? (
        <div className="flex flex-col h-full bg-[var(--color-surface)]">
          <div className="h-14 px-5 flex items-center border-b border-[var(--color-border)] shrink-0">
            <h2 className="text-[var(--font-size-2)] font-semibold text-[var(--color-ink-primary)]">研究上下文</h2>
          </div>
          <div className="flex-1 overflow-auto p-5 space-y-6">
            <div className="border-b border-[var(--color-border)] pb-5">
              <h3 className="text-[var(--font-size-2)] font-medium text-[var(--color-ink-primary)] mb-2">最终产物</h3>
              <p className="text-[var(--font-size-1)] text-[var(--color-ink-secondary)] mb-4">文献总结 · v3</p>
              <button onClick={onViewArtifact} className="text-[var(--font-size-1)] text-[var(--color-brand)] font-medium hover:underline underline-offset-2">查看产物 →</button>
            </div>
            <div className="border-b border-[var(--color-border)] pb-5">
              <h3 className="text-[var(--font-size-2)] font-medium text-[var(--color-ink-primary)] mb-2">证据覆盖</h3>
              <p className="text-[var(--font-size-1)] text-[var(--color-ink-secondary)] mb-1">3 / 4 已核验</p>
              <p className="text-[var(--font-size-1)] text-[var(--color-warning)] mb-4">1 项待验证</p>
              <button className="text-[var(--font-size-1)] text-[var(--color-brand)] font-medium hover:underline underline-offset-2">查看证据 →</button>
            </div>
            <div>
              <h3 className="text-[var(--font-size-2)] font-medium text-[var(--color-ink-primary)] mb-2">可复现性</h3>
              <p className="text-[var(--font-size-1)] text-[var(--color-ink-secondary)] mb-1">协议已冻结</p>
              <p className="text-[var(--font-size-1)] text-[var(--color-ink-secondary)] mb-4">研究包待生成</p>
              <button className="text-[var(--font-size-1)] text-[var(--color-brand)] font-medium hover:underline underline-offset-2">生成研究包 →</button>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex flex-col h-full bg-[var(--color-surface)] shadow-[-12px_0_28px_-4px_rgba(0,0,0,0.05)] z-10 absolute right-0 top-0 bottom-0 w-[384px] border-l border-[var(--color-border)]">
          <div className="h-14 px-5 flex items-center justify-between border-b border-[var(--color-border)] shrink-0 bg-[var(--color-surface)]">
            <button onClick={onCloseDetail} className="text-[var(--font-size-1)] text-[var(--color-ink-secondary)] hover:text-[var(--color-ink-primary)] font-medium">← 返回</button>
            <div className="flex items-center gap-4">
              <button className="text-[var(--font-size-1)] text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-primary)] font-medium">固定</button>
              <button onClick={onCloseDetail} className="text-[var(--font-size-1)] text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-primary)] font-medium">关闭</button>
            </div>
          </div>
          <div className="flex-1 overflow-auto p-6 space-y-8 bg-[var(--color-surface-muted)]">
            <div>
              <h3 className="text-[var(--font-size-0)] text-[var(--color-ink-tertiary)] mb-2 uppercase tracking-wider font-semibold">当前结论</h3>
              <p className="text-[var(--font-size-2)] text-[var(--color-ink-primary)] font-medium leading-relaxed bg-[var(--color-surface)] p-4 border border-[var(--color-border)] rounded-[4px]">
                “目录已注册 DOI 10.3847/1538-3881/ab3467”
              </p>
            </div>

            <div>
              <h3 className="text-[var(--font-size-2)] font-semibold text-[var(--color-ink-primary)] border-b border-[var(--color-border)] pb-2 mb-4">支持证据 3</h3>
              <div className="space-y-4">
                <div className="p-4 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[4px]">
                  <p className="text-[var(--font-size-1)] text-[var(--color-ink-secondary)] font-[var(--xw-font-serif)] italic border-l-[3px] border-[var(--color-border-strong)] pl-3">
                    The TESS Input Catalog (TIC) provides fundamental stellar parameters...
                  </p>
                </div>
                <div className="p-4 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[4px]">
                  <p className="text-[var(--font-size-1)] text-[var(--color-ink-secondary)] font-[var(--xw-font-serif)] italic border-l-[3px] border-[var(--color-border-strong)] pl-3">
                    Catalog metadata available at MAST...
                  </p>
                </div>
                <div className="p-4 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-[4px]">
                  <p className="text-[var(--font-size-1)] text-[var(--color-ink-secondary)] font-[var(--xw-font-serif)] italic border-l-[3px] border-[var(--color-border-strong)] pl-3">
                    DOI registration verified via Crossref API.
                  </p>
                </div>
              </div>
            </div>

            <div>
              <h3 className="text-[var(--font-size-2)] font-semibold text-[var(--color-ink-primary)] border-b border-[var(--color-border)] pb-2 mb-4">冲突证据 0</h3>
              <p className="text-[var(--font-size-1)] text-[var(--color-ink-tertiary)] italic px-2">无冲突证据</p>
            </div>

            <div>
              <h3 className="text-[var(--font-size-2)] font-semibold text-[var(--color-ink-primary)] border-b border-[var(--color-border)] pb-2 mb-4">来源</h3>
              <div className="bg-[var(--color-surface)] p-4 border border-[var(--color-border)] rounded-[4px] space-y-2">
                <p className="text-[var(--font-size-2)] text-[var(--color-ink-primary)] font-medium">The Revised TESS Input Catalog</p>
                <p className="text-[var(--font-size-0)] font-[var(--xw-font-mono)] text-[var(--color-ink-secondary)]">DOI: 10.3847/1538-3881/ab3467</p>
                <button className="text-[var(--font-size-1)] text-[var(--color-brand)] font-medium mt-1 hover:underline underline-offset-2">查看完整来源 →</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
