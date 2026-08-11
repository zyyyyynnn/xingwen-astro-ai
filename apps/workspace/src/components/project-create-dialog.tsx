import { useState, type FormEvent } from "react";
import {
  Alert,
  AlertDescription,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  Input,
  Textarea,
} from "@xingwen/ui";

interface ProjectCreateDialogProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onCreate: (input: {
    readonly name: string;
    readonly description: string;
  }) => Promise<void>;
  readonly pending: boolean;
  readonly errorMessage: string | null;
}

export function ProjectCreateDialog({
  open,
  onOpenChange,
  onCreate,
  pending,
  errorMessage,
}: ProjectCreateDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) return;
    await onCreate({ name: trimmedName, description: description.trim() });
    setName("");
    setDescription("");
  };

  return (
    <Dialog open={open} onOpenChange={pending ? undefined : onOpenChange}>
      <DialogContent aria-describedby="project-create-description">
        <DialogHeader>
          <DialogTitle>新建研究项目</DialogTitle>
          <DialogDescription id="project-create-description">
            项目承载持续的研究上下文。创建后将进入研究意图与协议确认流程。
          </DialogDescription>
        </DialogHeader>
        <form
          className="workspace-form"
          onSubmit={(event) => void submit(event)}
        >
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="project-name">项目名称</FieldLabel>
              <Input
                id="project-name"
                name="project-name"
                value={name}
                maxLength={160}
                required
                autoFocus
                disabled={pending}
                placeholder="例如：近邻系外行星宿主星比较"
                onChange={(event) => setName(event.currentTarget.value)}
              />
              <FieldDescription>
                使用便于在项目列表中识别的研究主题。
              </FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="project-description">研究说明</FieldLabel>
              <Textarea
                id="project-description"
                name="project-description"
                value={description}
                maxLength={2_000}
                disabled={pending}
                placeholder="补充对象范围、使用场景或预期结果（可选）"
                onChange={(event) => setDescription(event.currentTarget.value)}
              />
            </Field>
          </FieldGroup>
          {errorMessage ? (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage}</AlertDescription>
            </Alert>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="secondary"
              disabled={pending}
              onClick={() => onOpenChange(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={pending || !name.trim()}>
              {pending ? "正在创建…" : "创建并进入项目"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
