export function ChatMessagesSkeleton() {
  return (
    <div
      className="space-y-[var(--oh-space-3)] px-[var(--oh-space-5)] py-[var(--oh-space-4)]"
      aria-label="Agent 正在运行"
      aria-live="polite"
      role="status"
    >
      {["w-2/3", "w-5/6", "w-1/2"].map((width) => (
        <div
          key={width}
          className={`${width} h-[var(--oh-space-3)] animate-pulse rounded-[var(--oh-radius-xs)] bg-[var(--oh-skeleton)] motion-reduce:animate-none`}
        />
      ))}
      <span className="sr-only">Agent 正在运行</span>
    </div>
  );
}
