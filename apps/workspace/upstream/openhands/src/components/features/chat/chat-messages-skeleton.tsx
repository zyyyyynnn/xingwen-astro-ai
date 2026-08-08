export function ChatMessagesSkeleton() {
  return (
    <div
      className="space-y-3 px-5 py-4"
      aria-label="Agent 正在运行"
      aria-live="polite"
      role="status"
    >
      {["w-2/3", "w-5/6", "w-1/2"].map((width) => (
        <div
          key={width}
          className={`${width} h-3 animate-pulse rounded-[var(--oh-radius-xs)] bg-[var(--oh-skeleton)] motion-reduce:animate-none`}
        />
      ))}
      <span className="sr-only">Agent 正在运行</span>
    </div>
  );
}
