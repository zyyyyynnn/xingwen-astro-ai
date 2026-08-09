import { readFileSync } from "node:fs";
import { dirname, relative, resolve, sep } from "node:path";

function toPosix(path) {
  return path.split(sep).join("/");
}

function importedSpecifiers(source) {
  const specifiers = [];
  const staticImport =
    /\b(?:import|export)\s+(?:type\s+)?(?:[^"'`;]*?\s+from\s+)?["']([^"']+)["']/gu;
  const dynamicImport = /\bimport\(\s*["']([^"']+)["']\s*\)/gu;
  for (const pattern of [staticImport, dynamicImport]) {
    for (const match of source.matchAll(pattern)) specifiers.push(match[1]);
  }
  return specifiers;
}

function resolveLocalImport(root, sourceRoot, fromPath, specifier, diskPaths) {
  const cleanSpecifier = specifier.split("?", 1)[0];
  let base;
  if (cleanSpecifier.startsWith("#/")) {
    base = `${sourceRoot}/${cleanSpecifier.slice(2)}`;
  } else if (cleanSpecifier.startsWith(".")) {
    base = toPosix(
      relative(root, resolve(dirname(resolve(root, fromPath)), cleanSpecifier)),
    );
  } else {
    return { local: false, target: null };
  }

  if (!base.startsWith(`${sourceRoot}/`)) {
    return { local: true, target: null };
  }

  const candidates = [
    base,
    `${base}.ts`,
    `${base}.tsx`,
    `${base}.js`,
    `${base}.jsx`,
    `${base}/index.ts`,
    `${base}/index.tsx`,
    `${base}/index.js`,
    `${base}/index.jsx`,
  ];
  return {
    local: true,
    target: candidates.find((candidate) => diskPaths.has(candidate)) ?? null,
  };
}

export function analyzeVendoredImportGraph({
  root,
  sourceRoot,
  diskPaths,
  entrypoint = `${sourceRoot}/root.tsx`,
}) {
  const closure = new Set();
  const unresolved = [];
  const queue = diskPaths.has(entrypoint) ? [entrypoint] : [];

  while (queue.length > 0) {
    const current = queue.shift();
    if (!current || closure.has(current)) continue;
    closure.add(current);

    const source = readFileSync(resolve(root, current), "utf8");
    for (const specifier of importedSpecifiers(source)) {
      const resolved = resolveLocalImport(
        root,
        sourceRoot,
        current,
        specifier,
        diskPaths,
      );
      if (!resolved.local) continue;
      if (!resolved.target) {
        unresolved.push({ from: current, specifier });
      } else if (!closure.has(resolved.target)) {
        queue.push(resolved.target);
      }
    }
  }

  return {
    closure,
    unresolved,
    unreachable: [...diskPaths]
      .filter((path) => !closure.has(path))
      .sort((left, right) => left.localeCompare(right, "en")),
  };
}
