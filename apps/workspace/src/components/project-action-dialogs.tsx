import type { ProjectViewModel } from "@xingwen/research-adapter";
import {
  Alert,
  AlertDescription,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Field,
  FieldLabel,
  Input,
} from "@xingwen/ui";
import { useState } from "react";

interface ProjectActionDialogsProps {
  readonly renameProject: ProjectViewModel | null;
  readonly deleteProject: ProjectViewModel | null;
  readonly pending: boolean;
  readonly errorMessage: string | null;
  readonly onCloseRename: () => void;
  readonly onCloseDelete: () => void;
  readonly onRename: (name: string) => Promise<void>;
  readonly onDelete: () => Promise<void>;
}

function RenameProjectDialog({
  project,
  pending,
  errorMessage,
  onClose,
  onRename,
}: {
  readonly project: ProjectViewModel;
  readonly pending: boolean;
  readonly errorMessage: string | null;
  readonly onClose: () => void;
  readonly onRename: (name: string) => Promise<void>;
}) {
  const [name, setName] = useState(project.name);
  const valid = name.trim().length > 0 && name.trim().length <= 160;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>重命名研究项目</DialogTitle>
          <DialogDescription>
            新名称会同步更新左侧导航和当前项目标题。
          </DialogDescription>
        </DialogHeader>
        <Field data-invalid={!valid}>
          <FieldLabel htmlFor="rename-project-name">项目名称</FieldLabel>
          <Input
            id="rename-project-name"
            value={name}
            maxLength={160}
            disabled={pending}
            aria-invalid={!valid}
            autoFocus
            onChange={(event) => setName(event.currentTarget.value)}
          />
        </Field>
        {errorMessage ? (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        ) : null}
        <DialogFooter>
          <Button variant="secondary" disabled={pending} onClick={onClose}>
            取消
          </Button>
          <Button
            disabled={pending || !valid || name.trim() === project.name}
            onClick={() => void onRename(name.trim())}
          >
            {pending ? "正在保存…" : "保存名称"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ProjectActionDialogs({
  renameProject,
  deleteProject,
  pending,
  errorMessage,
  onCloseRename,
  onCloseDelete,
  onRename,
  onDelete,
}: ProjectActionDialogsProps) {
  return (
    <>
      {renameProject ? (
        <RenameProjectDialog
          key={`${renameProject.id}:${renameProject.revision}`}
          project={renameProject}
          pending={pending}
          errorMessage={errorMessage}
          onClose={onCloseRename}
          onRename={onRename}
        />
      ) : null}
      <AlertDialog
        open={deleteProject !== null}
        onOpenChange={(open) => !open && onCloseDelete()}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除研究项目？</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteProject
                ? `“${deleteProject.name}”及其研究对话、协议和运行引用将被删除。此操作不可撤销。`
                : "此操作不可撤销。"}
            </AlertDialogDescription>
          </AlertDialogHeader>
          {errorMessage ? (
            <Alert variant="destructive">
              <AlertDescription>{errorMessage}</AlertDescription>
            </Alert>
          ) : null}
          <AlertDialogFooter>
            <AlertDialogCancel disabled={pending}>取消</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={pending}
              onClick={() => void onDelete()}
            >
              {pending ? "正在删除…" : "删除项目"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
