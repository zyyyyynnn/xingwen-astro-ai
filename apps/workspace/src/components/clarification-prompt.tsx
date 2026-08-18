import { ChoicePrompt } from "./choice-prompt";

export interface ClarificationPromptProps {
  readonly id: string;
  readonly questionId: string;
  readonly question: string;
  readonly options: readonly string[];
  readonly answered: boolean;
  readonly selectedOption?: string | null;
  readonly isSubmitting?: boolean;
  readonly onAnswer: (questionId: string, answer: string) => void;
}

export function ClarificationPrompt({
  id,
  questionId,
  question,
  options,
  answered,
  selectedOption = null,
  isSubmitting = false,
  onAnswer,
}: ClarificationPromptProps) {
  if (options.length > 0) {
    return (
      <ChoicePrompt
        id={id}
        question={question}
        options={options}
        answered={answered}
        selectedOption={selectedOption}
        isSubmitting={isSubmitting}
        onSelect={(opt) => onAnswer(questionId, opt)}
      />
    );
  }

  if (answered && selectedOption) {
    return (
      <div
        className="xw-choice-prompt xw-choice-prompt--answered"
        data-testid={`clarification-answered-${id}`}
      >
        <p className="xw-choice-prompt__question">{question}</p>
        <div className="xw-choice-prompt__summary">
          <span className="xw-choice-prompt__badge">你的回答</span>
          <span className="xw-choice-prompt__answer">{selectedOption}</span>
        </div>
      </div>
    );
  }

  return (
    <div
      className="xw-choice-prompt xw-choice-prompt--active"
      data-testid={`clarification-active-${id}`}
    >
      <p className="xw-choice-prompt__question">{question}</p>
      <div className="xw-choice-prompt__help">
        请在下方输入框中输入你的回答以继续研究规划。
      </div>
    </div>
  );
}
