import type { DomainEntityId } from "@xingwen/domain";
import { Button } from "@xingwen/ui";
import { FileSearch } from "@xingwen/ui/icons";

export function EvidenceLinks({
  evidenceIds,
  label = "核验证据",
  onSelectEvidence,
}: {
  readonly evidenceIds: readonly DomainEntityId[];
  readonly label?: string;
  readonly onSelectEvidence?: (evidenceId: DomainEntityId) => void;
}) {
  if (!onSelectEvidence || evidenceIds.length === 0) return null;
  const visible = evidenceIds.slice(0, 3);
  return (
    <div className="evidence-links" aria-label={label}>
      {visible.map((evidenceId, index) => (
        <Button
          key={evidenceId}
          type="button"
          variant="ghost"
          size="small"
          title={evidenceId}
          onClick={() => onSelectEvidence(evidenceId)}
        >
          <FileSearch data-icon="inline-start" aria-hidden="true" />
          证据 {index + 1}
        </Button>
      ))}
      {evidenceIds.length > visible.length ? (
        <span>另有 {evidenceIds.length - visible.length} 条</span>
      ) : null}
    </div>
  );
}
