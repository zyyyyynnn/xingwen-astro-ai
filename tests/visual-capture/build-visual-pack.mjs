/**
 * Build the exact-head visual acceptance pack.
 *
 * This command intentionally refuses a dirty worktree: screenshots produced
 * from uncommitted source cannot truthfully be attributed to `git HEAD`.
 * Run: node tests/visual-capture/build-visual-pack.mjs <shotsDir> [exactHead]
 */
import { execFileSync, execSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  copyFileSync,
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { basename, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const repoRoot = execSync("git rev-parse --show-toplevel", {
  cwd: process.cwd(),
  encoding: "utf8",
}).trim();
const worktreeStatus = execSync(
  "git status --porcelain --untracked-files=all",
  { cwd: repoRoot, encoding: "utf8" },
).trim();
if (worktreeStatus) {
  throw new Error(
    "拒绝构建 exact-head 视觉包：工作区存在未提交修改。请先形成可审查提交，再重新捕获与构建。",
  );
}

const shotsDir = resolve(
  process.argv[2] ?? ".artifacts/visual-acceptance/shots",
);
const packDir = join(shotsDir, "..");
const actualHead = execSync("git rev-parse HEAD", {
  cwd: repoRoot,
  encoding: "utf8",
}).trim();
const requestedHead = process.argv[3] ?? actualHead;
if (requestedHead !== actualHead) {
  throw new Error(
    `请求的 exact HEAD ${requestedHead} 与当前 HEAD ${actualHead} 不一致。`,
  );
}

const PROJECT_A = "proj_01JEXAMPLE";
const PROJECT_B = "proj_toi_transit";
const PROJECT_C = "proj_l9859_spectroscopy";

const artifactShots = new Map([
  [
    "20_artifact-dataset",
    [PROJECT_A, "artv_dataset_01", ["数据表已渲染", "内部标识与单位已语义化"]],
  ],
  [
    "21_artifact-dataset-horizontal-scroll",
    [PROJECT_A, "artv_dataset_01", ["横向滚动已到达末端"]],
  ],
  [
    "22_artifact-field-dictionary",
    [PROJECT_A, "artv_fdict_01", ["字段定义可见"]],
  ],
  [
    "23_artifact-source-collection",
    [PROJECT_A, "artv_srccol_01", ["来源名称与状态使用用户语义"]],
  ],
  [
    "24_artifact-paper-collection",
    [PROJECT_A, "11111111-1111-4111-8111-111111111111", ["论文候选可见"]],
  ],
  [
    "24a_paper-summary-report",
    [PROJECT_A, "artv_papsum_01", ["研读报告优先可见"]],
  ],
  [
    "24b_paper-summary-with-pdf",
    [PROJECT_A, "artv_papsum_01", ["PDF 页数大于零", "页面 canvas 可见"]],
  ],
  [
    "24c_paper-evidence-jump",
    [PROJECT_A, "artv_papsum_01", ["证据跳转到目标页"]],
  ],
  [
    "30_artifact-literature-claims",
    [PROJECT_A, "artv_claims_01", ["科学主张可读"]],
  ],
  [
    "31_artifact-literature-relations",
    [PROJECT_A, "artv_rels_01", ["关系审定使用全宽工作区"]],
  ],
  [
    "32_relation-candidate-actions",
    [PROJECT_A, "artv_rels_01", ["候选关系主操作可见"]],
  ],
  ["33_relation-accepted", [PROJECT_A, "artv_rels_01", ["已接受关系状态可见"]]],
  [
    "34_relation-reasoning-trace",
    [PROJECT_A, "artv_rels_01", ["公开推导步骤已展开"]],
  ],
  ["36_artifact-graph", [PROJECT_A, "artv_graph_01", ["关系图 canvas 可见"]]],
  [
    "37_graph-selected-node",
    [PROJECT_A, "artv_graph_01", ["节点选中 inspector 可见"]],
  ],
  [
    "38_graph-selected-relation",
    [PROJECT_A, "artv_graph_01", ["关系边选中 inspector 可见"]],
  ],
  [
    "49_l9859-analysis-report",
    [PROJECT_C, "artv_c_analysis_01", ["L 98-59 分析报告无致命错误"]],
  ],
  [
    "50_analysis-report",
    [PROJECT_B, "artv_b_analysis_01", ["TOI-1233 分析内容可见"]],
  ],
  [
    "51_scientific-chart",
    [PROJECT_B, "artv_b_chart_01", ["Vega SVG ready", "SVG 宽度大于 240px"]],
  ],
  ["52_spectrum", [PROJECT_C, "artv_c_spec_01", ["L 98-59 光谱可见"]]],
  [
    "53_light-curve-time-series",
    [PROJECT_B, "artv_b_lc_01", ["时间序列视图可见"]],
  ],
  [
    "54_light-curve-phase-folded",
    [PROJECT_B, "artv_b_lc_01", ["相位折叠视图可见"]],
  ],
  [
    "55_light-curve-periodogram",
    [PROJECT_B, "artv_b_lc_01", ["周期图谱视图可见"]],
  ],
  [
    "55b_light-curve-peaks-expanded",
    [PROJECT_B, "artv_b_lc_01", ["峰值候选表已展开"]],
  ],
  [
    "56_model-evaluation",
    [PROJECT_B, "artv_b_modeval_01", ["基线对比可见", "无卡片墙"]],
  ],
  [
    "57_model-artifact",
    [PROJECT_B, "artv_b_model_01", ["ONNX 契约可见", "默认无校验哈希"]],
  ],
  ["58_fits-ready", [PROJECT_C, "artv_c_fits_01", ["FITS viewport ready"]]],
  ["59_wwt-ready", [PROJECT_C, "artv_c_wwt_01", ["WWT viewport ready"]]],
  [
    "60_wwt-grid-interaction",
    [PROJECT_C, "artv_c_wwt_01", ["坐标网格交互后再次 ready"]],
  ],
  [
    "71_long-content-scrolled-bottom",
    [PROJECT_A, "artv_claims_01", ["长内容可滚动到底部"]],
  ],
]);

const projectShots = new Map([
  ["10_project-overview", [PROJECT_A, ["研究概览可见"]]],
  ["11_project-b-overview", [PROJECT_B, ["Project B 研究线程可见"]]],
  ["11b_project-b-results", [PROJECT_B, ["Project B 结果索引可见"]]],
  ["12_project-c-overview", [PROJECT_C, ["Project C 研究线程可见"]]],
  ["12b_project-c-results", [PROJECT_C, ["Project C 结果索引可见"]]],
  ["11_message-stream-top", [PROJECT_A, ["用户与助手消息可见"]]],
  ["11b_message-stream-mid", [PROJECT_A, ["中部活动与结果可见"]]],
  ["11c_message-stream-bottom", [PROJECT_A, ["线程底部可达"]]],
  ["12_inspector-results", [PROJECT_A, ["右侧结果索引可见"]]],
  ["13_protocol-review-dialog", [PROJECT_A, ["研究协议可见"]]],
  ["80_viewport-1440x900", [PROJECT_A, ["1440 桌面布局"]]],
  ["81_viewport-1280x800", [PROJECT_A, ["1280 桌面布局"]]],
  ["82_viewport-1024x768", [PROJECT_A, ["1024 图标侧栏", "主线程可读"]]],
]);

const shellShots = new Map([
  ["01_workspace-index", ["/workspace", ["工作台入口可见"]]],
  ["02_sidebar-collapsed", ["/workspace", ["侧栏收起状态可见"]]],
  ["03_command-menu", ["/workspace", ["项目导航命令可见"]]],
  ["04_model-provider-dialog", ["/workspace", ["模型服务对话框可见"]]],
]);

function metadataFor(name) {
  const artifact = artifactShots.get(name);
  if (artifact) {
    const [projectId, versionId, assertions] = artifact;
    return {
      project_id: projectId,
      route: `/workspace/${projectId} → Thread 结果 → 全屏 → 返回研究`,
      entry_method: "normal_path",
      artifact_version_id: versionId,
      viewport: "1440x900",
      required_assertions: assertions,
    };
  }
  const project = projectShots.get(name);
  if (project) {
    const [projectId, assertions] = project;
    const viewport = name.includes("1024")
      ? "1024x768"
      : name.includes("1280")
        ? "1280x800"
        : "1440x900";
    return {
      project_id: projectId,
      route: `/workspace/${projectId}`,
      entry_method: "normal_path",
      artifact_version_id: null,
      viewport,
      required_assertions: assertions,
    };
  }
  const shell = shellShots.get(name);
  if (shell) {
    return {
      project_id: null,
      route: shell[0],
      entry_method: "normal_path",
      artifact_version_id: null,
      viewport: "1440x900",
      required_assertions: shell[1],
    };
  }
  if (name === "40_share-dialog" || name === "41_share-dialog-with-link") {
    return {
      project_id: PROJECT_A,
      route: `/workspace/${PROJECT_A} → Dataset → 分享`,
      entry_method: "normal_path",
      artifact_version_id: "artv_dataset_01",
      viewport: "1440x900",
      required_assertions: [
        name === "40_share-dialog" ? "分享设置可见" : "新建分享链接可见",
      ],
    };
  }
  if (
    name === "42_created-public-share" ||
    name === "43_invalid-public-share"
  ) {
    return {
      project_id: null,
      route:
        name === "42_created-public-share"
          ? "/share/<created-token>"
          : "/share/token_invalid_revoked",
      entry_method:
        name === "42_created-public-share"
          ? "created_share_link"
          : "public_error_path",
      artifact_version_id:
        name === "42_created-public-share" ? "artv_dataset_01" : null,
      viewport: "1440x900",
      required_assertions: [
        name === "42_created-public-share"
          ? "本次创建的公开页可见"
          : "失效分享错误态可见",
      ],
    };
  }
  throw new Error(`截图 ${name} 缺少显式 route/assertion 元数据。`);
}

const files = readdirSync(shotsDir)
  .filter((file) => file.endsWith(".png"))
  .sort();
if (files.length === 0)
  throw new Error("截图目录为空。请先运行 visual capture。");

const expectedNames = new Set([
  ...artifactShots.keys(),
  ...projectShots.keys(),
  ...shellShots.keys(),
  "40_share-dialog",
  "41_share-dialog-with-link",
  "42_created-public-share",
  "43_invalid-public-share",
]);
const actualNames = new Set(files.map((file) => basename(file, ".png")));
const missing = [...expectedNames].filter((name) => !actualNames.has(name));
const unexpected = [...actualNames].filter((name) => !expectedNames.has(name));
if (missing.length || unexpected.length) {
  throw new Error(
    `截图集合不完整。missing=[${missing.join(", ")}], unexpected=[${unexpected.join(", ")}]`,
  );
}

const entries = files.map((file) => {
  const bytes = readFileSync(join(shotsDir, file));
  const name = basename(file, ".png");
  return {
    name,
    exact_head: actualHead,
    ...metadataFor(name),
    file,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    bytes: bytes.length,
  };
});

const byHash = new Map();
for (const entry of entries) {
  const existing = byHash.get(entry.sha256);
  if (existing) {
    throw new Error(`像素重复：${existing.name} === ${entry.name}`);
  }
  byHash.set(entry.sha256, entry);
}

writeFileSync(
  join(packDir, "manifest.json"),
  JSON.stringify(
    {
      exact_head: actualHead,
      generated_at: new Date().toISOString(),
      execution_mode: "demo_replay",
      viewport_default: "1440x900",
      shots: entries,
    },
    null,
    2,
  ),
  "utf8",
);

const columns = 3;
const rows = Math.ceil(entries.length / columns);
const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>PR #258 visual acceptance — ${actualHead.slice(0, 10)}</title>
<style>
body{margin:0;padding:16px;background:#111418;color:#e5e7eb;font:12px system-ui}
h1{font-size:18px}.grid{display:grid;grid-template-columns:repeat(${columns},1fr);gap:12px}
figure{margin:0;overflow:hidden;border:1px solid #38404a;background:#1b1f24}
img{display:block;width:100%;min-height:120px;background:#0c0f12}
figcaption{padding:8px;color:#b8c0ca;word-break:break-word}
</style><h1>PR #258 视觉验收 · HEAD ${actualHead.slice(0, 10)} · ${entries.length} shots</h1>
<div class="grid">${entries.map((entry) => `<figure><img src="shots/${entry.file}"><figcaption>${entry.name}<br>${entry.entry_method} · ${entry.viewport}</figcaption></figure>`).join("\n")}</div></html>`;
const contactHtml = join(packDir, "contact-sheet.html");
writeFileSync(contactHtml, html, "utf8");

const { chromium } = await import("@playwright/test");
const browser = await chromium.launch();
try {
  const page = await browser.newPage({
    viewport: { width: 1800, height: 1000 },
  });
  await page.goto(pathToFileURL(contactHtml).href);
  await page.locator("img").last().waitFor({ state: "visible" });
  await page.screenshot({
    path: join(packDir, "contact-sheet.png"),
    fullPage: true,
  });
} finally {
  await browser.close();
}

const zipPath = join(
  packDir,
  `visual-acceptance-${actualHead.slice(0, 10)}.zip`,
);
const staging = join(packDir, "_zip");
rmSync(zipPath, { force: true });
rmSync(staging, { recursive: true, force: true });
mkdirSync(staging, { recursive: true });
copyFileSync(join(packDir, "manifest.json"), join(staging, "manifest.json"));
copyFileSync(contactHtml, join(staging, "contact-sheet.html"));
copyFileSync(
  join(packDir, "contact-sheet.png"),
  join(staging, "contact-sheet.png"),
);
cpSync(shotsDir, join(staging, "shots"), { recursive: true });
const quotePowerShell = (value) => `'${value.replaceAll("'", "''")}'`;
execFileSync(
  "powershell.exe",
  [
    "-NoProfile",
    "-NonInteractive",
    "-Command",
    `Compress-Archive -Path ${quotePowerShell(join(staging, "*"))} -DestinationPath ${quotePowerShell(zipPath)} -Force`,
  ],
  { cwd: repoRoot, stdio: "inherit" },
);
rmSync(staging, { recursive: true, force: true });

if (!existsSync(zipPath)) throw new Error("视觉验收 ZIP 未生成。");
console.log(
  `visual pack: ${entries.length} shots, ${rows}x${columns}, ${zipPath}`,
);
