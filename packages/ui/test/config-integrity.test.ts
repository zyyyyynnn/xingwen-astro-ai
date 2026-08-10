import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const root = resolve(process.cwd(), "../..");

function collectRuntimeExports(filePath: string, content: string): Set<string> {
  const sourceFile = ts.createSourceFile(
    filePath,
    content,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const runtimeExports = new Set<string>();

  for (const statement of sourceFile.statements) {
    if (ts.isExportDeclaration(statement)) {
      if (statement.isTypeOnly) continue;
      if (statement.exportClause && ts.isNamedExports(statement.exportClause)) {
        for (const element of statement.exportClause.elements) {
          if (!element.isTypeOnly) {
            runtimeExports.add(element.name.text);
          }
        }
      }
    } else if (
      (ts.isFunctionDeclaration(statement) ||
        ts.isClassDeclaration(statement) ||
        ts.isVariableStatement(statement)) &&
      statement.modifiers?.some((m) => m.kind === ts.SyntaxKind.ExportKeyword)
    ) {
      if (ts.isVariableStatement(statement)) {
        for (const decl of statement.declarationList.declarations) {
          if (ts.isIdentifier(decl.name)) {
            runtimeExports.add(decl.name.text);
          }
        }
      } else if (statement.name && ts.isIdentifier(statement.name)) {
        runtimeExports.add(statement.name.text);
      }
    }
  }

  return runtimeExports;
}

describe("@xingwen/ui foundation config integrity", () => {
  it("resolves package internal subpath imports via TypeScript compiler host", () => {
    const tsconfigPath = resolve(process.cwd(), "tsconfig.json");
    const configFile = ts.readConfigFile(tsconfigPath, ts.sys.readFile);
    const parsedConfig = ts.parseJsonConfigFileContent(
      configFile.config,
      ts.sys,
      process.cwd(),
    );

    const compilerOptions = parsedConfig.options;
    const containingFile = resolve(process.cwd(), "src/index.ts");

    const resolvedComponentsButton = ts.bundlerModuleNameResolver(
      "#components/button",
      containingFile,
      compilerOptions,
      ts.sys,
    );
    expect(resolvedComponentsButton.resolvedModule).toBeDefined();
    expect(resolvedComponentsButton.resolvedModule?.resolvedFileName).toContain(
      "src/button.tsx",
    );

    const resolvedButton = ts.bundlerModuleNameResolver(
      "#ui/button",
      containingFile,
      compilerOptions,
      ts.sys,
    );
    expect(resolvedButton.resolvedModule).toBeDefined();
    expect(resolvedButton.resolvedModule?.resolvedFileName).toContain(
      "src/button.tsx",
    );

    const resolvedUtils = ts.bundlerModuleNameResolver(
      "#utils",
      containingFile,
      compilerOptions,
      ts.sys,
    );
    expect(resolvedUtils.resolvedModule).toBeDefined();
    expect(resolvedUtils.resolvedModule?.resolvedFileName).toContain(
      "src/lib/utils.ts",
    );

    const resolvedLibUtils = ts.bundlerModuleNameResolver(
      "#lib/utils",
      containingFile,
      compilerOptions,
      ts.sys,
    );
    expect(resolvedLibUtils.resolvedModule).toBeDefined();
    expect(resolvedLibUtils.resolvedModule?.resolvedFileName).toContain(
      "src/lib/utils.ts",
    );
  });

  it("aligns components.json aliases with resolvable package imports", () => {
    const componentsConfig = JSON.parse(
      readFileSync(resolve(process.cwd(), "components.json"), "utf8"),
    );
    const manifest = JSON.parse(
      readFileSync(resolve(process.cwd(), "package.json"), "utf8"),
    );

    expect(componentsConfig.aliases.components).toBe("#components");
    expect(componentsConfig.aliases.utils).toBe("#utils");
    expect(componentsConfig.aliases.ui).toBe("#ui");
    expect(componentsConfig.aliases.lib).toBe("#lib");

    const imports = manifest.imports;
    expect(imports["#components/*"]).toBe("./src/*.tsx");
    expect(imports["#utils"]).toBe("./src/lib/utils.ts");
    expect(imports["#ui/*"]).toBe("./src/*.tsx");
    expect(imports["#lib/*"]).toBe("./src/lib/*.ts");

    const utilsPath = resolve(process.cwd(), imports["#utils"]);
    expect(existsSync(utilsPath)).toBe(true);
  });

  it("maintains immutable provenance, exact commit, and valid notices for adopted components", () => {
    const catalog = JSON.parse(
      readFileSync(resolve(process.cwd(), "component-sources.json"), "utf8"),
    );

    const names = new Set<string>();
    const paths = new Set<string>();

    for (const item of catalog.components) {
      expect(item.name).toBeTruthy();
      expect(names.has(item.name)).toBe(false);
      names.add(item.name);

      expect(item.local_path).toBeTruthy();
      expect(paths.has(item.local_path)).toBe(false);
      paths.add(item.local_path);
      expect(existsSync(resolve(root, item.local_path))).toBe(true);

      expect(item.source).toMatch(/^@shadcn\//);
      expect(item.upstream_repository).toBe("https://github.com/shadcn-ui/ui");
      expect(item.upstream_revision).toBe("shadcn-ui@0.9.4");
      expect(item.upstream_commit).toMatch(/^[0-9a-f]{40}$/);
      expect(item.registry_item).toBeTruthy();
      expect(item.license).toBe("MIT");
      expect(item.notice).toBeTruthy();
      expect(existsSync(resolve(root, item.notice))).toBe(true);
      expect(item.adaptation).toContain("clsx");
      expect(item.adaptation).not.toContain("dependency-free");
      expect(item.production_consumers.length).toBeGreaterThan(0);
    }
  });

  it("ensures all cataloged adopted components are public runtime value exports via AST and dynamic import", async () => {
    const catalog = JSON.parse(
      readFileSync(resolve(process.cwd(), "component-sources.json"), "utf8"),
    );
    const indexContent = readFileSync(
      resolve(process.cwd(), "src/index.ts"),
      "utf8",
    );

    const runtimeExports = collectRuntimeExports("src/index.ts", indexContent);
    const importedModule = await import("../src/index");

    for (const item of catalog.components) {
      expect(runtimeExports.has(item.name)).toBe(true);
      expect(
        typeof (importedModule as Record<string, unknown>)[item.name],
      ).toBe("function");
    }
  });
});
