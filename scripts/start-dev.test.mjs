import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { resolve } from "node:path";

const repositoryRoot = resolve(import.meta.dirname, "..");
const startDevPath = resolve(repositoryRoot, "start-dev.bat");
const workspacePackagePath = resolve(
  repositoryRoot,
  "apps",
  "workspace",
  "package.json",
);

const startDevBytes = readFileSync(startDevPath);
const startDev = startDevBytes.toString("utf8").replaceAll("\r\n", "\n");
const workspacePackage = JSON.parse(readFileSync(workspacePackagePath, "utf8"));

test("start-dev.bat uses CMD-compatible CRLF line endings", () => {
  let crlfCount = 0;
  let loneLfCount = 0;

  for (let index = 0; index < startDevBytes.length; index += 1) {
    if (startDevBytes[index] !== 0x0a) continue;
    if (startDevBytes[index - 1] === 0x0d) {
      crlfCount += 1;
    } else {
      loneLfCount += 1;
    }
  }

  assert.ok(crlfCount > 0, "the batch file must contain CRLF line endings");
  assert.equal(loneLfCount, 0, "the batch file must not contain lone LF bytes");
});

test("start-dev.bat uses Prelude-compatible PowerShell argument passing", () => {
  assert.doesNotMatch(startDev, /\bpwsh\b/iu);
  assert.match(startDev, /call\s+:require_command\s+powershell/iu);
  assert.match(
    startDev,
    /powershell\s+-NoProfile\s+-ExecutionPolicy\s+Bypass\s+-Command\s+"\$port\s*=\s*%~1;/iu,
  );
  assert.match(
    startDev,
    /powershell\s+-NoProfile\s+-ExecutionPolicy\s+Bypass\s+-Command\s+"\$url\s*=\s*'%~1';/iu,
  );
  assert.doesNotMatch(
    startDev,
    /\$env:(?:CHECK_PORT|CHECK_URL|CHECK_TIMEOUT)/iu,
  );
});

test("start-dev.bat starts local services in standard CMD windows", () => {
  assert.match(startDev, /title\s+Xingwen Preflight/iu);
  assert.match(
    startDev,
    /if\s+\/i\s+"%~1"=="--preflight"[\s\S]*?start\s+"Xingwen Preflight"\s+cmd\s+\/k/iu,
  );
  assert.match(startDev, /start\s+"Xingwen Backend"\s+cmd\s+\/k/iu);
  assert.match(startDev, /start\s+"Xingwen Frontend"\s+cmd\s+\/k/iu);
  assert.match(
    startDev,
    /call\s+pnpm\s+install\s+--frozen-lockfile\s+>nul\s+2>&1/iu,
  );
  assert.match(
    startDev,
    /uv\s+sync\s+--project\s+"%API_DIR%"\s+--frozen\s+>nul\s+2>&1/iu,
  );
  assert.match(
    startDev,
    /docker\s+compose\s+-p\s+%COMPOSE_PROJECT_NAME%\s+up\s+-d\s+--wait\s+postgres\s+>nul\s+2>&1/iu,
  );
  assert.match(startDev, /uv\s+run\s+alembic\s+upgrade\s+head\s+>nul\s+2>&1/iu);
  assert.doesNotMatch(startDev, /start\s+"Xingwen Backend"[^\r\n]*>nul\b/iu);
  assert.doesNotMatch(startDev, /start\s+"Xingwen Frontend"[^\r\n]*>nul\b/iu);
  assert.doesNotMatch(startDev, /start\s+"[^"]+"\s+pwsh\b/iu);
});

test("workspace Vite keeps the preflight port stable", () => {
  assert.match(workspacePackage.scripts.dev, /--strictPort\b/u);
});
