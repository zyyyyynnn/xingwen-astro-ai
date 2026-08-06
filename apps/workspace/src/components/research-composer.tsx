import { useState, type FormEvent } from "react";

export interface AttachedObject {
  readonly id: string;
  readonly label: string;
  readonly kind: "artifact" | "evidence" | "source";
}

export interface ResearchComposerProps {
  readonly mode: "docked" | "focus";
  readonly onSubmit: (
    input: string,
    attachedObjects?: readonly AttachedObject[],
  ) => void;
  readonly onModeChange?: (mode: "docked" | "focus") => void;
  readonly disabled?: boolean;
  readonly placeholder?: string;
  readonly attachedObjects?: readonly AttachedObject[];
  readonly attachableCandidates?: readonly AttachedObject[];
  readonly onAttachObject?: (object: AttachedObject) => void;
  readonly onDetachObject?: (id: string) => void;
}

const QUICK_ACTIONS = [
  { id: "check-evidence", label: "检查证据", snippet: "请检查证据覆盖率" },
  { id: "generate-artifact", label: "生成产物", snippet: "请生成数据产物" },
  { id: "review-sources", label: "复核来源", snippet: "请复核来源" },
] as const;

const KIND_LABELS: Record<AttachedObject["kind"], string> = {
  artifact: "产物",
  evidence: "证据",
  source: "来源",
};

/** Docked bottom composer with docked/focus states and object attachment. */
export function ResearchComposer({
  mode,
  onSubmit,
  onModeChange,
  disabled = false,
  placeholder = "继续研究…",
  attachedObjects = [],
  attachableCandidates = [],
  onAttachObject,
  onDetachObject,
}: ResearchComposerProps) {
  const [value, setValue] = useState("");
  const [scope, setScope] = useState<"current" | "project">("current");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed, attachedObjects);
    setValue("");
    onModeChange?.("docked");
  };

  const handleFocus = () => {
    if (mode === "docked") {
      onModeChange?.("focus");
    }
  };

  const handleBlur = () => {
    if (mode === "focus" && !value.trim() && attachedObjects.length === 0) {
      onModeChange?.("docked");
    }
  };

  const handleQuickAction = (snippet: string) => {
    setValue((prev) => {
      const base = prev.trim();
      return base ? `${base}\n${snippet}` : snippet;
    });
  };

  if (mode === "docked") {
    return (
      <form
        className="research-composer research-composer--docked"
        onSubmit={handleSubmit}
      >
        <input
          type="text"
          className="research-composer__input"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onFocus={handleFocus}
          placeholder={placeholder}
          disabled={disabled}
          aria-label="研究输入"
        />
        {attachedObjects.length > 0 ? (
          <span
            className="research-composer__attachment-count"
            aria-label={`已附加 ${attachedObjects.length} 个对象`}
          >
            {attachedObjects.length}
          </span>
        ) : null}
        <button
          type="submit"
          className="research-composer__submit"
          disabled={disabled || !value.trim()}
        >
          提交
        </button>
      </form>
    );
  }

  return (
    <form
      className="research-composer research-composer--focus"
      onSubmit={handleSubmit}
    >
      <textarea
        className="research-composer__textarea"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={handleBlur}
        placeholder={placeholder}
        disabled={disabled}
        aria-label="研究输入"
        rows={4}
      />
      {attachedObjects.length > 0 ? (
        <ul className="research-composer__attachments" aria-label="已附加对象">
          {attachedObjects.map((object) => (
            <li key={object.id} className="research-composer__attachment">
              <span className="research-composer__attachment-kind">
                {KIND_LABELS[object.kind]}
              </span>
              <span className="research-composer__attachment-label">
                {object.label}
              </span>
              {onDetachObject ? (
                <button
                  type="button"
                  className="research-composer__attachment-remove"
                  onClick={() => onDetachObject(object.id)}
                  disabled={disabled}
                  aria-label={`移除 ${object.label}`}
                >
                  ×
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {attachableCandidates.length > 0 && onAttachObject ? (
        <details className="research-composer__candidates">
          <summary>附加对象（{attachableCandidates.length}）</summary>
          <ul className="research-composer__candidate-list">
            {attachableCandidates.map((candidate) => (
              <li key={candidate.id}>
                <button
                  type="button"
                  className="research-composer__candidate"
                  onClick={() => onAttachObject(candidate)}
                  disabled={disabled}
                >
                  <span className="research-composer__candidate-kind">
                    {KIND_LABELS[candidate.kind]}
                  </span>
                  <span className="research-composer__candidate-label">
                    {candidate.label}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <div className="research-composer__toolbar">
        <label className="research-composer__scope">
          作用范围
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value as "current" | "project")}
            disabled={disabled}
          >
            <option value="current">当前 Mission</option>
            <option value="project">整个 Project</option>
          </select>
        </label>
        <div className="research-composer__quick-actions">
          {QUICK_ACTIONS.map((action) => (
            <button
              key={action.id}
              type="button"
              className="research-composer__quick-action"
              onClick={() => handleQuickAction(action.snippet)}
              disabled={disabled}
            >
              {action.label}
            </button>
          ))}
        </div>
        <button
          type="submit"
          className="research-composer__submit"
          disabled={disabled || !value.trim()}
        >
          提交
        </button>
      </div>
    </form>
  );
}
