export function MissionNavigator() {
  return (
    <div className="w-[224px] border-r border-[var(--color-border)] bg-[var(--color-surface)] flex flex-col shrink-0">
      <div className="p-4 border-b border-[var(--color-border)] shrink-0">
        <button className="w-full text-left px-3 py-2 border border-[var(--color-border-strong)] rounded-[4px] text-[var(--font-size-1)] font-semibold text-[var(--color-ink-primary)] hover:bg-[var(--color-surface-hover)] transition-colors flex items-center justify-center">
          + 新建研究
        </button>
      </div>
      <div className="flex-1 overflow-auto py-2">
        
        {/* 正在进行 */}
        <div className="mb-4">
          <div className="px-4 py-2 text-[var(--font-size-0)] font-semibold text-[var(--color-ink-tertiary)] uppercase tracking-wider">正在进行</div>
          <button className="w-full text-left px-4 py-3 flex flex-col gap-1 hover:bg-[var(--color-surface-muted)] transition-colors border-l-2 border-transparent">
            <span className="text-[var(--font-size-2)] text-[var(--color-ink-primary)] font-medium leading-snug line-clamp-2">TESS 候选体筛选</span>
            <span className="text-[var(--font-size-0)] text-[var(--color-ink-secondary)]">证据采集 · 12 分钟前</span>
          </button>
        </div>

        {/* 待复核 */}
        <div className="mb-4">
          <div className="px-4 py-2 text-[var(--font-size-0)] font-semibold text-[var(--color-ink-tertiary)] uppercase tracking-wider">待复核</div>
          <button className="w-full text-left px-4 py-3 flex flex-col gap-1 hover:bg-[var(--color-surface-muted)] transition-colors border-l-2 border-transparent">
            <span className="text-[var(--font-size-2)] text-[var(--color-ink-primary)] font-medium leading-snug line-clamp-2">宿主恒星参数验证</span>
            <span className="text-[var(--font-size-0)] text-[var(--color-warning)] font-medium">2 项待复核</span>
          </button>
        </div>

        {/* 已完成 */}
        <div className="mb-4">
          <div className="px-4 py-2 text-[var(--font-size-0)] font-semibold text-[var(--color-ink-tertiary)] uppercase tracking-wider">已完成</div>
          <button className="w-full text-left px-4 py-3 flex flex-col gap-1 bg-[var(--color-surface-muted)] border-l-2 border-[var(--color-focus)]">
            <span className="text-[var(--font-size-2)] text-[var(--color-ink-primary)] font-semibold leading-snug line-clamp-2">TESS 候选目标清单分析</span>
            <span className="text-[var(--font-size-0)] text-[var(--color-ink-secondary)]">15 分钟前</span>
          </button>
        </div>

        {/* 最近访问 */}
        <div>
          <div className="px-4 py-2 text-[var(--font-size-0)] font-semibold text-[var(--color-ink-tertiary)] uppercase tracking-wider">最近访问</div>
          <button className="w-full text-left px-4 py-3 flex flex-col gap-1 hover:bg-[var(--color-surface-muted)] transition-colors border-l-2 border-transparent">
            <span className="text-[var(--font-size-2)] text-[var(--color-ink-secondary)] font-medium leading-snug line-clamp-2">固定项目</span>
          </button>
        </div>
      </div>
    </div>
  );
}
