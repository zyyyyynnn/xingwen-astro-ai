import {
  Badge,
  Button,
  FieldDescription,
  FieldGroup,
  FieldLegend,
  FieldSet,
  Input,
  RadioGroup,
  RadioGroupItem,
} from "@xingwen/ui";
import { useState } from "react";

/** One selectable choice; at most one option should carry the recommended marker. */
export interface ChoicePromptOption {
  readonly value: string;
  readonly recommended?: boolean;
}

const FREE_CHOICE_VALUE = "__free_choice__";

export interface ChoicePromptProps {
  readonly id: string;
  readonly question: string;
  readonly description?: string | null;
  readonly options: readonly string[] | readonly ChoicePromptOption[];
  readonly answered: boolean;
  readonly selectedOption?: string | null;
  readonly freeText?: string | null;
  readonly allowFreeText?: boolean;
  readonly isSubmitting?: boolean;
  readonly onSelect: (option: string, freeText?: string) => void;
}

function normalizeOptions(
  options: readonly string[] | readonly ChoicePromptOption[],
): readonly ChoicePromptOption[] {
  return options.map((option) =>
    typeof option === "string" ? { value: option } : option,
  );
}

/**
 * The one shared choice interaction primitive for clarification questions and
 * Run checkpoints. No option is auto-selected; the explicit 自行说明 choice is
 * the only path to free text; an answered prompt is immutable.
 */
export function ChoicePrompt({
  id,
  question,
  description = null,
  options,
  answered,
  selectedOption = null,
  freeText = null,
  allowFreeText = false,
  isSubmitting = false,
  onSelect,
}: ChoicePromptProps) {
  const normalized = normalizeOptions(options);
  const [selected, setSelected] = useState<string | null>(
    selectedOption ?? null,
  );
  const [customText, setCustomText] = useState<string>(freeText ?? "");
  const choseFree = selected === FREE_CHOICE_VALUE;
  const canSubmit =
    selected !== null && (!choseFree || customText.trim().length > 0);

  if (answered && (selectedOption || freeText)) {
    const answeredFree =
      selectedOption === FREE_CHOICE_VALUE || !selectedOption;
    return (
      <div
        className="xw-choice-prompt xw-choice-prompt--answered"
        data-testid={`choice-prompt-answered-${id}`}
      >
        <div className="xw-choice-prompt__header">
          <p className="xw-choice-prompt__question">{question}</p>
          <Badge variant="secondary">已回答</Badge>
        </div>
        <p className="xw-choice-prompt__summary">
          <span className="sr-only">已选择：</span>
          <span className="xw-choice-prompt__answer">
            {answeredFree ? (freeText ?? "") : selectedOption}
          </span>
        </p>
      </div>
    );
  }

  return (
    <div
      className="xw-choice-prompt xw-choice-prompt--active"
      data-testid={`choice-prompt-active-${id}`}
    >
      <FieldSet className="xw-choice-prompt__fields">
        <FieldLegend className="xw-choice-prompt__question">
          {question}
        </FieldLegend>
        {description ? (
          <FieldDescription
            id={`${id}-description`}
            className="xw-choice-prompt__description"
          >
            {description}
          </FieldDescription>
        ) : null}
        <FieldGroup className="xw-choice-prompt__fields">
          <RadioGroup
            value={selected ?? undefined}
            onValueChange={setSelected}
            className="xw-choice-prompt__options"
            aria-label={question}
            aria-describedby={description ? `${id}-description` : undefined}
          >
            {normalized.map((option, index) => {
              const itemId = `${id}-opt-${index}`;
              return (
                <label
                  key={option.value}
                  htmlFor={itemId}
                  className={`xw-choice-prompt__option ${selected === option.value ? "is-selected" : ""}`}
                >
                  <RadioGroupItem value={option.value} id={itemId} />
                  <span className="xw-choice-prompt__option-label">
                    {option.value}
                  </span>
                  {option.recommended ? (
                    <Badge variant="secondary">推荐</Badge>
                  ) : null}
                </label>
              );
            })}
            {allowFreeText ? (
              <label
                htmlFor={`${id}-opt-free`}
                className={`xw-choice-prompt__option ${choseFree ? "is-selected" : ""}`}
              >
                <RadioGroupItem
                  value={FREE_CHOICE_VALUE}
                  id={`${id}-opt-free`}
                />
                <span className="xw-choice-prompt__option-label">自行说明</span>
              </label>
            ) : null}
          </RadioGroup>
          {allowFreeText && choseFree ? (
            <div className="xw-choice-prompt__free-text">
              <Input
                placeholder="用自己的话说明（必填）"
                value={customText}
                aria-label="自行说明内容"
                onChange={(e) => setCustomText(e.target.value)}
              />
            </div>
          ) : null}
          <div className="xw-choice-prompt__actions">
            <Button
              disabled={!canSubmit || isSubmitting}
              onClick={() => {
                if (selected === null) return;
                if (selected === FREE_CHOICE_VALUE) {
                  onSelect(FREE_CHOICE_VALUE, customText.trim());
                } else {
                  onSelect(selected, undefined);
                }
              }}
            >
              {isSubmitting ? "正在提交..." : "确认选择"}
            </Button>
          </div>
        </FieldGroup>
      </FieldSet>
    </div>
  );
}
