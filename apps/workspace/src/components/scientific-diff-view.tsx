import type { ScientificDiffResult } from "../presentation/scientific-diff";

const CATEGORY_LABELS = {
  contract: "研究契约",
  sources: "来源集合",
  conclusions: "结论",
  evidence: "证据",
  relations: "关系",
  limitations: "限制与冲突",
} as const;

const CHANGE_LABELS = {
  added: "新增",
  removed: "移除",
  changed: "变化",
} as const;

export interface ScientificDiffViewProps {
  readonly results: readonly ScientificDiffResult[];
}

export function ScientificDiffView({ results }: ScientificDiffViewProps) {
  const changedCategories = results.filter(
    (result) => result.changes.length > 0,
  );

  if (changedCategories.length === 0) {
    return (
      <div className="scientific-diff-empty" role="status">
        <h3>没有发现科学内容变化</h3>
        <p>所选结果的研究契约、来源与科学内容保持一致。</p>
      </div>
    );
  }

  return (
    <div className="scientific-diff" aria-label="科学结果变化">
      {changedCategories.map((result) => (
        <section className="scientific-diff-category" key={result.category}>
          <h3>{CATEGORY_LABELS[result.category]}</h3>
          <ul className="scientific-diff-list">
            {result.changes.map((change) => (
              <li
                className="scientific-diff-change"
                key={`${result.category}:${change.key}`}
              >
                <p className="scientific-diff-change-kind">
                  {CHANGE_LABELS[change.kind]}
                </p>
                {change.kind === "changed" ? (
                  <div className="scientific-diff-before-after">
                    <div>
                      <span>原有内容</span>
                      <p>{change.before}</p>
                    </div>
                    <div>
                      <span>当前内容</span>
                      <p>{change.after}</p>
                    </div>
                  </div>
                ) : (
                  <p>{change.after ?? change.before}</p>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
