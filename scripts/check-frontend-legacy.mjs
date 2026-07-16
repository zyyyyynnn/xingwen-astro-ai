import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import process from "node:process";

const root = process.cwd();
const frameworkName = String.fromCharCode(118, 117, 101);
const retiredApp = ["apps", "web"].join("/");
const retiredTerms = [
  ["@vitejs", `plugin-${frameworkName}`].join("/"),
  `${frameworkName}-tsc`,
  `shadcn-${frameworkName}`,
  `reka-${"ui"}`,
  `lucide-${frameworkName}-next`,
  `@${frameworkName}use/`,
  `@${frameworkName}-flow/`,
  `${frameworkName}-router`,
  `pi${"nia"}`,
  retiredApp,
  String.fromCharCode(26087, 21069, 31471),
  String.fromCharCode(36801, 31227, 28304),
  String.fromCharCode(22238, 36864, 21069, 31471),
  ["WEB", "PORT"].join("_"),
];
const forbiddenLockNames = [
  "package-lock.json",
  "yarn.lock",
  "bun.lock",
  "bun.lockb",
];
const textFilePattern =
  /(?:^|\/)(?:[^/]+\.(?:astro|css|html|js|json|jsx|md|mjs|toml|ts|tsx|txt|yaml|yml)|Dockerfile)$/u;

const files = execFileSync("git", ["ls-files", "-co", "--exclude-standard"], {
  cwd: root,
  encoding: "utf8",
})
  .split(/\r?\n/u)
  .filter(Boolean)
  .map((file) => file.replaceAll("\\", "/"));

const failures = [];

for (const file of files) {
  if (file === retiredApp || file.startsWith(`${retiredApp}/`)) {
    failures.push(`${file}: retired application path remains.`);
  }
  if (file.endsWith(`.${frameworkName}`)) {
    failures.push(`${file}: retired component extension remains.`);
  }
  if (forbiddenLockNames.some((name) => file.endsWith(name))) {
    failures.push(`${file}: unsupported dependency lock remains.`);
  }
  if (!textFilePattern.test(file)) {
    continue;
  }

  const content = readFileSync(resolve(root, file), "utf8");
  for (const term of retiredTerms) {
    if (content.includes(term)) {
      failures.push(
        `${file}: contains retired runtime term ${JSON.stringify(term)}.`,
      );
    }
  }
}

if (failures.length > 0) {
  console.error("Frontend retirement check failed:\n");
  for (const failure of failures) {
    console.error(`- ${failure}`);
  }
  process.exit(1);
}

console.log("Frontend retirement check passed.");
