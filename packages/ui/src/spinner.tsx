interface SpinnerProps {
  className?: string;
  label?: string;
}

export function Spinner({ className, label = "加载中" }: SpinnerProps) {
  const combined = ["xw-spinner", className].filter(Boolean).join(" ");
  return (
    <span className={combined} role="status" aria-live="polite">
      <span className="xw-spinner__dot" aria-hidden="true" />
      <span className="xw-spinner__label">{label}</span>
    </span>
  );
}
