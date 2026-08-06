export function MainStage({ 
  currentView, 
  onViewArtifact,
  onBack,
  onOpenEvidence
}: {
  currentView: "summary" | "artifact";
  onViewArtifact: () => void;
  onBack: () => void;
  onOpenEvidence: () => void;
}) {
  if (currentView === "artifact") {
    return (
      <div className="max-w-[720px] mx-auto p-4 font-[var(--xw-font-serif)]">
        <button onClick={onBack} className="mb-8 text-[var(--font-size-1)] text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-primary)] font-[var(--xw-font-sans)] transition-colors">
          ← 返回摘要
        </button>
        <div className="mb-10 font-[var(--xw-font-sans)]">
          <div className="text-[var(--font-size-0)] text-[var(--color-ink-secondary)] uppercase tracking-wider mb-2 font-medium">Paper Summary • v3</div>
          <h2 className="text-[var(--font-size-6)] font-bold text-[var(--color-ink-primary)] leading-tight tracking-tight" style={{ textWrap: 'balance' }}>
            TESS 候选目标清单文献总结
          </h2>
        </div>
        <div className="prose prose-slate max-w-none prose-p:leading-[1.7] prose-p:text-[var(--font-size-3)] prose-p:text-[var(--color-ink-primary)] text-[var(--color-ink-primary)]">
          <p className="mb-4">本文献总结整合了修订版 TESS Input Catalog (TIC) 的相关研究。TIC 为 TESS 任务提供基础的恒星参数，主要用于在观测视野内优先选择可能具有凌星行星的矮星。</p>
          <p>我们发现在交叉验证过程中，部分候选体的宿主恒星参数与 Gaia DR3 的最新结果存在系统性偏差。虽然 TIC 已经过多次修订，但对于处于观测边缘的低质量矮星样本，缺乏直接的引用证据。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[720px] mx-auto pb-20">
      {/* 1. Completion Hero */}
      <section className="mb-12">
        <div className="text-[var(--font-size-1)] font-semibold text-[var(--color-success)] mb-2">研究已完成</div>
        <h2 className="text-[var(--font-size-5)] font-[var(--xw-font-serif)] font-bold text-[var(--color-ink-primary)] mb-4">TESS 候选目标清单分析</h2>
        <p className="text-[var(--font-size-3)] text-[var(--color-ink-secondary)] leading-[1.6]">
          本研究整合修订版 TESS Input Catalog 与宿主恒星参数，<br/>
          形成可用于候选目标优先排序的结构化结果。
        </p>
      </section>

      {/* 2. Final Conclusion */}
      <section className="mb-12 border-t border-[var(--color-border)] pt-8">
        <h3 className="text-[var(--font-size-2)] font-semibold text-[var(--color-ink-primary)] mb-4">最终结论</h3>
        <p className="text-[var(--font-size-3)] font-[var(--xw-font-serif)] text-[var(--color-ink-primary)] leading-[1.7]">
          修订版目录能够为候选目标优先级评估提供统一的恒星参数和测光、视差来源，但对低质量或缺失测量的目标仍需单独复核。
        </p>
      </section>

      {/* 3. Key Findings */}
      <section className="mb-12 border-t border-[var(--color-border)] pt-8">
        <h3 className="text-[var(--font-size-2)] font-semibold text-[var(--color-ink-primary)] mb-5">关键发现</h3>
        <div className="space-y-6">
          <div className="flex gap-3">
            <div className="mt-1 text-[var(--color-success)] font-bold text-[var(--font-size-2)]">✓</div>
            <div>
              <p className="text-[var(--font-size-2)] text-[var(--color-ink-primary)] font-medium mb-1">目录已注册 DOI 10.3847/1538-3881/ab3467</p>
              <button onClick={onOpenEvidence} className="text-[var(--font-size-0)] text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-primary)] transition-colors underline decoration-[var(--color-border-strong)] underline-offset-4">
                3 条支持证据 · 查看来源
              </button>
            </div>
          </div>
          <div className="flex gap-3">
            <div className="mt-1 text-[var(--color-warning)] font-bold text-[var(--font-size-2)]">△</div>
            <div>
              <p className="text-[var(--font-size-2)] text-[var(--color-ink-primary)] font-medium mb-1">部分候选体的宿主恒星参数存在来源差异</p>
              <button onClick={onOpenEvidence} className="text-[var(--font-size-0)] text-[var(--color-ink-tertiary)] hover:text-[var(--color-ink-primary)] transition-colors underline decoration-[var(--color-border-strong)] underline-offset-4">
                2 条支持证据 · 1 条冲突证据
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* 4. Final Artifacts */}
      <section className="mb-12 border-t border-[var(--color-border)] pt-8">
        <h3 className="text-[var(--font-size-2)] font-semibold text-[var(--color-ink-primary)] mb-4">最终产物</h3>
        <div className="flex flex-col border border-[var(--color-border)] rounded-[4px] bg-[var(--color-surface)] overflow-hidden">
          <button className="flex justify-between items-center px-4 py-3 border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors text-left" onClick={onViewArtifact}>
            <span className="text-[var(--font-size-2)] text-[var(--color-ink-primary)] font-medium">候选目标数据集</span>
            <span className="text-[var(--font-size-1)] text-[var(--color-ink-tertiary)] font-[var(--xw-font-mono)]">Dataset · v2</span>
          </button>
          <button className="flex justify-between items-center px-4 py-3 border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors text-left" onClick={onViewArtifact}>
            <span className="text-[var(--font-size-2)] text-[var(--color-ink-primary)] font-medium">规范字段字典</span>
            <span className="text-[var(--font-size-1)] text-[var(--color-ink-tertiary)] font-[var(--xw-font-mono)]">Field Dictionary · v1</span>
          </button>
          <button className="flex justify-between items-center px-4 py-3 hover:bg-[var(--color-surface-hover)] transition-colors text-left" onClick={onViewArtifact}>
            <span className="text-[var(--font-size-2)] text-[var(--color-ink-primary)] font-medium">文献总结</span>
            <span className="text-[var(--font-size-1)] text-[var(--color-ink-tertiary)] font-[var(--xw-font-mono)]">Paper Summary · v3</span>
          </button>
        </div>
      </section>

      {/* 5. Limitations and Unresolved */}
      <section className="mb-12 border-t border-[var(--color-border)] pt-8">
        <div className="grid grid-cols-2 gap-8">
          <div>
            <h3 className="text-[var(--font-size-2)] font-semibold text-[var(--color-ink-primary)] mb-4">已知局限</h3>
            <ul className="list-disc pl-4 space-y-2 text-[var(--font-size-2)] text-[var(--color-ink-secondary)] marker:text-[var(--color-border-strong)]">
              <li>部分矮星样本缺乏直接引用证据</li>
              <li>目录完整性受观测波段限制</li>
            </ul>
          </div>
          <div>
            <h3 className="text-[var(--font-size-2)] font-semibold text-[var(--color-ink-primary)] mb-4">未解决问题</h3>
            <ul className="list-disc pl-4 space-y-2 text-[var(--font-size-2)] text-[var(--color-ink-secondary)] marker:text-[var(--color-border-strong)]">
              <li>3 个候选体仍存在来源参数冲突</li>
              <li>1 个结论需要补充光谱观测验证</li>
            </ul>
          </div>
        </div>
      </section>

      {/* 6. Recommended Next Steps */}
      <section className="border-t border-[var(--color-border)] pt-8">
        <h3 className="text-[var(--font-size-2)] font-semibold text-[var(--color-ink-primary)] mb-4">建议下一步</h3>
        <div className="flex flex-col gap-3 items-start">
          <button className="text-[var(--font-size-2)] text-[var(--color-brand)] font-medium hover:underline underline-offset-4">验证 3 个参数冲突的候选体 →</button>
          <button className="text-[var(--font-size-2)] text-[var(--color-brand)] font-medium hover:underline underline-offset-4">补充 Gaia DR4 来源 →</button>
          <button className="text-[var(--font-size-2)] text-[var(--color-brand)] font-medium hover:underline underline-offset-4">基于当前结果派生目标优先级研究 →</button>
        </div>
      </section>
    </div>
  );
}
