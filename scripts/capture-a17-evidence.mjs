/**
 * A-17 Homepage Visual — drift-correction evidence capture.
 *
 * Run AFTER the site dev server is up on http://127.0.0.1:4321/.
 * Produces, under docs/evidence/a17-homepage-visual/:
 *   - desktop-1440x900.png        Full homepage at desktop viewport
 *   - mobile-390x844.png          Full homepage at mobile viewport
 *   - motion-loop.webm            One full 5.6s+ loop recording
 *   - frame-1-full.png            Complete phase (densest frame in loop)
 *   - frame-2-converge.png        Converge phase (descending midpoint)
 *   - frame-3-near-empty.png      Near-empty phase (sparsest frame in loop)
 *   - frame-4-rebuild.png         Rebuild phase (ascending midpoint)
 *   - detail-200pct.png           200% zoom on the main body
 *   - dither-glyph-test.png       Cropped glyph lattice for dither readout
 *   - frame-stats.json            Per-sample stats for the loop
 *
 * Usage:  node scripts/capture-a17-evidence.mjs
 */
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync, readdirSync, renameSync } from "node:fs";
import { resolve } from "node:path";

const OUT = resolve("docs/evidence/a17-homepage-visual");
mkdirSync(OUT, { recursive: true });
const SITE = "http://127.0.0.1:4321/";

async function forcePreservedDrawingBuffer(page) {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (...args) {
      const kind = String(args[0] ?? "");
      if (kind.startsWith("webgl")) {
        const opts =
          typeof args[1] === "object" && args[1] !== null ? { ...args[1] } : {};
        opts.preserveDrawingBuffer = true;
        args[1] = opts;
      }
      return original.apply(this, args);
    };
  });
}

async function readStats(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector(".hero-canvas canvas");
    if (!canvas) return null;
    const gl = canvas.getContext("webgl2");
    if (!gl) return null;
    const w = canvas.width;
    const h = canvas.height;
    const px = new Uint8Array(w * h * 4);
    gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
    let paper = 0;
    let glyph = 0;
    let black = 0;
    for (let i = 0; i < px.length; i += 4) {
      const r = px[i] ?? 0;
      const g = px[i + 1] ?? 0;
      const b = px[i + 2] ?? 0;
      const min = Math.min(r, g, b);
      if (r < 12 && g < 12 && b < 12) black++;
      if (r >= 230 && g >= 230 && b >= 230) paper++;
      else if (min < 205) glyph++;
    }
    const total = w * h;
    return {
      width: w,
      height: h,
      paperRatio: paper / total,
      glyphRatio: glyph / total,
      blackRatio: black / total,
    };
  });
}

async function waitForReady(page) {
  await page.goto(SITE);
  await page.waitForSelector(".hero-canvas canvas", { timeout: 15_000 });
  await page.waitForFunction(
    () =>
      document.querySelector(".hero-poster")?.hasAttribute("hidden") === true,
    { timeout: 15_000 },
  );
}

/**
 * Sample one full motion loop and identify the four phase frames.
 * Phases are derived from the glyphRatio signal shape, not from a clock:
 *   full       = local maximum of glyphRatio (densest)
 *   near-empty = local minimum of glyphRatio (sparsest)
 *   converge   = descending midpoint between full and the next near-empty
 *   rebuild    = ascending midpoint between near-empty and the next full
 */
async function sampleLoop(page, durationMs) {
  const samples = [];
  const start = Date.now();
  while (Date.now() - start < durationMs) {
    const stats = await readStats(page);
    if (stats) samples.push({ t: Date.now() - start, ...stats });
    await page.waitForTimeout(40);
  }
  return samples;
}

function findPhaseFrames(samples) {
  if (samples.length < 10) throw new Error("not enough samples");
  let fullIdx = 0;
  let emptyIdx = 0;
  for (let i = 0; i < samples.length; i++) {
    if (samples[i].glyphRatio > samples[fullIdx].glyphRatio) fullIdx = i;
    if (samples[i].glyphRatio < samples[emptyIdx].glyphRatio) emptyIdx = i;
  }
  const fullRatio = samples[fullIdx].glyphRatio;
  const emptyRatio = samples[emptyIdx].glyphRatio;
  const mid = (fullRatio + emptyRatio) / 2;

  // Converge: first sample after fullIdx where ratio <= mid, heading toward empty.
  let convergeIdx = -1;
  for (let i = fullIdx + 1; i < samples.length; i++) {
    if (samples[i].glyphRatio <= mid) {
      convergeIdx = i;
      break;
    }
  }
  // Rebuild: first sample after emptyIdx where ratio >= mid, heading toward full.
  let rebuildIdx = -1;
  for (let i = emptyIdx + 1; i < samples.length; i++) {
    if (samples[i].glyphRatio >= mid) {
      rebuildIdx = i;
      break;
    }
  }

  // Fallbacks if the loop boundary cut a phase short.
  if (convergeIdx === -1) convergeIdx = Math.floor((fullIdx + emptyIdx) / 2);
  if (rebuildIdx === -1) rebuildIdx = Math.floor((emptyIdx + samples.length - 1) / 2);

  return {
    full: { idx: fullIdx, sample: samples[fullIdx] },
    converge: { idx: convergeIdx, sample: samples[convergeIdx] },
    nearEmpty: { idx: emptyIdx, sample: samples[emptyIdx] },
    rebuild: { idx: rebuildIdx, sample: samples[rebuildIdx] },
    fullRatio,
    emptyRatio,
    mid,
  };
}

async function main() {
  const browser = await chromium.launch({ headless: true });

  // ---- Desktop: video + loop sampling + keyframes ----
  const desktopCtx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: OUT, size: { width: 1440, height: 900 } },
  });
  const desktopPage = await desktopCtx.newPage();
  await forcePreservedDrawingBuffer(desktopPage);
  await waitForReady(desktopPage);

  // Sample ~12s (>2 loops) to cover every phase at least twice.
  const samples = await sampleLoop(desktopPage, 12_000);
  const phases = findPhaseFrames(samples);

  // Re-wait for each phase and capture. We monitor live and capture when
  // glyphRatio is close to the target ratio and moving in the right direction.
  const targets = [
    {
      name: "frame-1-full",
      ratio: phases.fullRatio,
      direction: "peak",
    },
    {
      name: "frame-2-converge",
      ratio: phases.mid,
      direction: "down",
    },
    {
      name: "frame-3-near-empty",
      ratio: phases.emptyRatio,
      direction: "valley",
    },
    {
      name: "frame-4-rebuild",
      ratio: phases.mid,
      direction: "up",
    },
  ];

  const tolerance = (phases.fullRatio - phases.emptyRatio) * 0.12 || 0.005;
  const captured = {};
  let prevRatio = null;
  const captureStart = Date.now();
  let targetIdx = 0;

  while (targetIdx < targets.length && Date.now() - captureStart < 40_000) {
    const stats = await readStats(desktopPage);
    if (stats) {
      const r = stats.glyphRatio;
      const target = targets[targetIdx];
      const close = Math.abs(r - target.ratio) <= tolerance;
      let match = false;
      if (close && prevRatio !== null) {
        if (target.direction === "peak") match = r <= prevRatio; // just past peak
        else if (target.direction === "valley") match = r >= prevRatio; // just past valley
        else if (target.direction === "down") match = r < prevRatio;
        else if (target.direction === "up") match = r > prevRatio;
      }
      if (match) {
        await desktopPage.screenshot({
          path: resolve(OUT, `${target.name}.png`),
        });
        captured[target.name] = { glyphRatio: r, ...stats };
        targetIdx++;
      }
      prevRatio = r;
    }
    await desktopPage.waitForTimeout(30);
  }

  // Wait for the next full-open phase before capturing detail/dither/desktop.
  // Full-open ≈ glyphRatio within 15% of the observed peak.
  const fullThreshold = phases.fullRatio * 0.85;
  const fullDeadline = Date.now() + 20_000;
  while (Date.now() < fullDeadline) {
    const stats = await readStats(desktopPage);
    if (stats && stats.glyphRatio >= fullThreshold) break;
    await desktopPage.waitForTimeout(40);
  }

  // Full desktop screenshot at full-open.
  await desktopPage.screenshot({ path: resolve(OUT, "desktop-1440x900.png") });

  // Find the glyph-densest region of the canvas for accurate detail clips.
  // Scan the canvas in a grid and return the center of the densest tile.
  const denseCenter = await desktopPage.evaluate(() => {
    const canvas = document.querySelector(".hero-canvas canvas");
    if (!canvas) return null;
    const gl = canvas.getContext("webgl2");
    if (!gl) return null;
    const w = canvas.width;
    const h = canvas.height;
    const px = new Uint8Array(w * h * 4);
    gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
    const rect = canvas.getBoundingClientRect();
    // Tile the canvas into 4x4 grid; find the tile with most glyph pixels.
    const tiles = 4;
    let best = { count: -1, cx: w / 2, cy: h / 2 };
    for (let ty = 0; ty < tiles; ty++) {
      for (let tx = 0; tx < tiles; tx++) {
        let count = 0;
        const x0 = Math.floor((tx * w) / tiles);
        const x1 = Math.floor(((tx + 1) * w) / tiles);
        const y0 = Math.floor((ty * h) / tiles);
        const y1 = Math.floor(((ty + 1) * h) / tiles);
        for (let y = y0; y < y1; y += 2) {
          for (let x = x0; x < x1; x += 2) {
            const i = (y * w + x) * 4;
            const r = px[i] ?? 0;
            const g = px[i + 1] ?? 0;
            const b = px[i + 2] ?? 0;
            const min = Math.min(r, g, b);
            if (r < 230 || g < 230 || b < 230) {
              if (min < 205) count++;
            }
          }
        }
        if (count > best.count) {
          best = {
            count,
            cx: Math.floor((x0 + x1) / 2),
            cy: Math.floor((y0 + y1) / 2),
          };
        }
      }
    }
    // Convert canvas-internal coords to viewport coords.
    const scaleX = rect.width / w;
    const scaleY = rect.height / h;
    return {
      vx: rect.left + best.cx * scaleX,
      vy: rect.top + best.cy * scaleY,
    };
  });

  // 200% detail — clip a 360x280 window centered on the densest region.
  const dc = denseCenter || { vx: 782, vy: 446 };
  const detailClip = {
    x: Math.max(0, Math.round(dc.vx - 180)),
    y: Math.max(0, Math.round(dc.vy - 140)),
    width: 360,
    height: 280,
  };
  await desktopPage.screenshot({
    path: resolve(OUT, "detail-200pct.png"),
    clip: detailClip,
    scale: "device",
  });

  // Dither/glyph test image — tight 220x150 crop centered on the core.
  const glyphClip = {
    x: Math.max(0, Math.round(dc.vx - 110)),
    y: Math.max(0, Math.round(dc.vy - 75)),
    width: 220,
    height: 150,
  };
  await desktopPage.screenshot({
    path: resolve(OUT, "dither-glyph-test.png"),
    clip: glyphClip,
    scale: "device",
  });

  // Stop video recording (saves on context close).
  await desktopPage.close();
  await desktopCtx.close();

  // ---- Mobile screenshot ----
  const mobileCtx = await browser.newContext({
    viewport: { width: 390, height: 844 },
  });
  const mobilePage = await mobileCtx.newPage();
  await forcePreservedDrawingBuffer(mobilePage);
  await waitForReady(mobilePage);
  await mobilePage.waitForTimeout(1200);
  await mobilePage.screenshot({ path: resolve(OUT, "mobile-390x844.png") });
  await mobileCtx.close();

  // ---- Write stats ----
  const summary = {
    generatedAt: new Date().toISOString(),
    phases,
    captured,
    sampleCount: samples.length,
    samples: samples.map((s) => ({
      t: s.t,
      glyphRatio: s.glyphRatio,
      paperRatio: s.paperRatio,
      blackRatio: s.blackRatio,
    })),
  };
  writeFileSync(resolve(OUT, "frame-stats.json"), JSON.stringify(summary, null, 2));

  // Rename Playwright's random .webm to motion-loop.webm.
  for (const file of readdirSync(OUT)) {
    if (file.endsWith(".webm")) {
      try {
        renameSync(resolve(OUT, file), resolve(OUT, "motion-loop.webm"));
      } catch {
        /* best-effort */
      }
    }
  }

  console.log("Evidence captured to", OUT);
  console.log("Files:", readdirSync(OUT));
  console.log("Phases:", {
    full: phases.fullRatio.toFixed(4),
    converge: phases.mid.toFixed(4),
    nearEmpty: phases.emptyRatio.toFixed(4),
    rebuild: phases.mid.toFixed(4),
  });
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
