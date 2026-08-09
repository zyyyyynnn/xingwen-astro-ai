import { createHash } from "node:crypto";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { relative, resolve, sep } from "node:path";

export function toPosix(path) {
  return path.split(sep).join("/");
}

export function listVendoredFiles(directory) {
  const files = [];
  for (const entry of readdirSync(directory)) {
    const absolute = resolve(directory, entry);
    if (statSync(absolute).isDirectory()) {
      files.push(...listVendoredFiles(absolute));
    } else if (statSync(absolute).isFile()) {
      files.push(absolute);
    }
  }
  return files.sort((left, right) =>
    toPosix(relative(directory, left)).localeCompare(
      toPosix(relative(directory, right)),
      "en",
    ),
  );
}

export function computeSelectedTreeSha256(directory, relativePaths) {
  const digest = createHash("sha256");
  for (const path of [...new Set(relativePaths)].sort((left, right) =>
    left.localeCompare(right, "en"),
  )) {
    const absolutePath = resolve(directory, path);
    digest.update(path, "utf8");
    digest.update("\0");
    digest.update(readFileSync(absolutePath));
    digest.update("\0");
  }
  return digest.digest("hex");
}
