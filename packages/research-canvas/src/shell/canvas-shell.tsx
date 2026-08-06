import { useState } from "react";
import { MissionNavigator } from "../navigation/mission-navigator";
import { MainStage } from "../stage/main-stage";
import { ContextDock } from "../context/context-dock";

export function CanvasShell() {
  const [currentView, setCurrentView] = useState<"summary" | "artifact">("summary");
  const [dockMode, setDockMode] = useState<"summary" | "detail">("summary");

  return (
    <div className="flex h-screen w-full overflow-hidden bg-[var(--color-canvas)] text-[var(--color-ink-primary)] font-[var(--xw-font-sans)]">
      {/* 宽屏默认界面 - 左侧 */}
      <MissionNavigator />
      
      <div className="flex-1 flex flex-col min-w-0 bg-[var(--color-canvas)] relative">
        <header className="border-b border-[var(--color-border)] px-6 py-4 shrink-0 bg-[var(--color-surface)] flex flex-col gap-2">
           <div className="flex items-center justify-between">
             <div className="flex items-center gap-3">
               <h1 className="text-[var(--font-size-3)] font-semibold text-[var(--color-ink-primary)] tracking-tight">星文智析 | TESS 候选目标清单分析</h1>
             </div>
             <div className="flex items-center gap-4 text-[var(--font-size-1)] text-[var(--color-ink-secondary)]">
               <button className="hover:text-[var(--color-ink-primary)] transition-colors">命令面板</button>
               <button className="hover:text-[var(--color-ink-primary)] transition-colors">导出</button>
               <button className="hover:text-[var(--color-ink-primary)] transition-colors">分享</button>
             </div>
           </div>
           {/* Mission Spine */}
           <div className="flex items-center text-[var(--font-size-1)] font-[var(--xw-font-mono)] text-[var(--color-ink-tertiary)] mt-1 tracking-wide">
             <span className="text-[var(--color-ink-secondary)] font-semibold">问题定义</span>
             <span className="mx-2">→</span>
             <span className="text-[var(--color-ink-secondary)] font-semibold">协议确认</span>
             <span className="mx-2">→</span>
             <span className="text-[var(--color-ink-secondary)] font-semibold">证据采集</span>
             <span className="mx-2">→</span>
             <span className="text-[var(--color-ink-secondary)] font-semibold">分析验证</span>
             <span className="mx-2">→</span>
             <span className="text-[var(--color-ink-secondary)] font-semibold">结论形成</span>
             <span className="mx-2">→</span>
             <span className="text-[var(--color-success)] font-bold">复核交付</span>
           </div>
        </header>
        
        <div className="flex-1 overflow-auto bg-[var(--color-canvas)] p-8">
          <MainStage 
            currentView={currentView} 
            onViewArtifact={() => setCurrentView("artifact")}
            onBack={() => setCurrentView("summary")}
            onOpenEvidence={() => setDockMode("detail")}
          />
        </div>
        
        {/* 底部动作栏 (替代被禁用的 Composer) */}
        {currentView === "summary" && (
          <div className="shrink-0 p-5 border-t border-[var(--color-border)] bg-[var(--color-surface)] flex justify-start gap-4">
            <button className="px-5 py-2 rounded-[4px] bg-[var(--color-brand)] text-[var(--color-brand-on)] font-semibold text-[var(--font-size-1)] hover:bg-[var(--color-brand-hover)] transition-colors">
              继续研究
            </button>
            <button className="px-5 py-2 rounded-[4px] border border-[var(--color-border-strong)] bg-transparent text-[var(--color-ink-primary)] font-medium text-[var(--font-size-1)] hover:bg-[var(--color-surface-hover)] transition-colors">
              请求修订
            </button>
            <button className="px-5 py-2 rounded-[4px] border border-[var(--color-border-strong)] bg-transparent text-[var(--color-ink-primary)] font-medium text-[var(--font-size-1)] hover:bg-[var(--color-surface-hover)] transition-colors">
              派生任务
            </button>
            <button className="px-5 py-2 rounded-[4px] border border-[var(--color-border-strong)] bg-transparent text-[var(--color-ink-primary)] font-medium text-[var(--font-size-1)] hover:bg-[var(--color-surface-hover)] transition-colors">
              导出
            </button>
          </div>
        )}
      </div>

      <ContextDock 
        mode={dockMode}
        onCloseDetail={() => setDockMode("summary")}
        onViewArtifact={() => setCurrentView("artifact")}
      />
    </div>
  );
}
