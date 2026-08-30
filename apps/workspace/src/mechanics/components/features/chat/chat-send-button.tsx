import { Button } from "@xingwen/ui";
import { ArrowUp } from "@xingwen/ui/icons";

interface ChatSendButtonProps {
  readonly handleSubmit: () => void;
  readonly disabled: boolean;
  readonly submitting: boolean;
}

export function ChatSendButton({
  handleSubmit,
  disabled,
  submitting,
}: ChatSendButtonProps) {
  return (
    <Button
      size="icon-xsmall"
      className="rounded-[var(--radius-pill)]"
      data-testid="submit-button"
      aria-label={submitting ? "正在发送研究消息" : "发送研究消息"}
      onClick={handleSubmit}
      disabled={disabled}
    >
      <ArrowUp aria-hidden="true" />
    </Button>
  );
}
