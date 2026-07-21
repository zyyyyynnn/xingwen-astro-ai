interface BrandMarkProps {
  showSubtitle?: boolean;
  className?: string;
}

export function BrandMark({ showSubtitle = false, className }: BrandMarkProps) {
  const combined = ["xw-brand-mark", className].filter(Boolean).join(" ");
  return (
    <span className={combined}>
      <span className="xw-brand-mark__title">星文智析</span>
      {showSubtitle ? (
        <span className="xw-brand-mark__subtitle">XINGWEN ASTRO AI</span>
      ) : null}
    </span>
  );
}
