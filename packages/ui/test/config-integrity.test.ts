import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const root = resolve(process.cwd(), "../..");

describe("@xingwen/ui foundation config integrity", () => {
  it("aligns components.json aliases with resolvable package imports", () => {
    const componentsConfig = JSON.parse(
      readFileSync(resolve(process.cwd(), "components.json"), "utf8"),
    );
    const manifest = JSON.parse(
      readFileSync(resolve(process.cwd(), "package.json"), "utf8"),
    );

    expect(componentsConfig.aliases.utils).toBe("#utils");
    expect(componentsConfig.aliases.ui).toBe("#ui");

    const imports = manifest.imports;
    expect(imports["#utils"]).toBe("./src/lib/utils.ts");
    expect(imports["#ui/*"]).toBe("./src/*");

    const utilsPath = resolve(process.cwd(), imports["#utils"]);
    expect(existsSync(utilsPath)).toBe(true);
  });

  it("maintains immutable provenance and valid notices for adopted components", () => {
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
      expect(item.upstream_repository).toBeTruthy();
      expect(item.upstream_revision).not.toMatch(/^(?:main|master|latest)$/i);
      expect(item.license).toBe("MIT");
      expect(item.notice).toBeTruthy();
      expect(existsSync(resolve(root, item.notice))).toBe(true);
      expect(item.adaptation).toBeTruthy();
      expect(item.production_consumers.length).toBeGreaterThan(0);
    }
  });

  it("ensures all cataloged adopted components are public exports", () => {
    const catalog = JSON.parse(
      readFileSync(resolve(process.cwd(), "component-sources.json"), "utf8"),
    );
    const indexContent = readFileSync(
      resolve(process.cwd(), "src/index.ts"),
      "utf8",
    );

    for (const item of catalog.components) {
      expect(indexContent).toContain(item.name);
    }
  });
});
