import { mkdirSync, rmSync } from "node:fs";
import { resolve } from "node:path";

export default function globalSetup(): void {
  const shotDirectory =
    process.env.VISUAL_SHOT_DIR ??
    resolve(".artifacts/visual-acceptance/shots");
  rmSync(shotDirectory, { recursive: true, force: true });
  mkdirSync(shotDirectory, { recursive: true });
}
