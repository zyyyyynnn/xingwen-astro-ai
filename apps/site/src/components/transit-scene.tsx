import { useEffect, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import type {
  Quality,
  ResearchSceneModel,
  ScenePalette,
} from "@xingwen/visual-engine";

import {
  createDynamicRenderer,
  type DynamicRenderer,
} from "./visual/dynamic-renderer";

export type TransitStatus = "unavailable" | "lost" | "restored" | "ready";

interface TransitSceneProps {
  model: ResearchSceneModel;
  palette: ScenePalette;
  quality: Quality;
  reducedMotion: boolean;
  freezeTime: number;
  onStatus?: (status: TransitStatus) => void;
}

/**
 * R3F Site Adapter — owns the WebGL canvas lifecycle (via the R3F Canvas)
 * and drives the Site Visual Adapter's `DynamicRenderer`.
 *
 * Render ownership: `useFrame` is registered with priority `1`, which
 * disables R3F's default automatic render loop. The DynamicRenderer's
 * internal `gl.render(scene, camera)` is therefore the single
 * authoritative draw call — the empty R3F scene graph can never clear
 * the canvas to black. Reduced motion renders a single static phase
 * (`renderAt`) on invalidated frames instead of a continuous loop.
 */
export function TransitScene({
  model,
  palette,
  quality,
  reducedMotion,
  freezeTime,
  onStatus,
}: TransitSceneProps) {
  const gl = useThree((state) => state.gl);
  const size = useThree((state) => state.size);
  const invalidate = useThree((state) => state.invalidate);
  const rendererRef = useRef<DynamicRenderer | null>(null);
  const onStatusRef = useRef(onStatus);
  useEffect(() => {
    onStatusRef.current = onStatus;
  });

  useEffect(() => {
    let renderer: DynamicRenderer | null = null;
    try {
      renderer = createDynamicRenderer({
        gl,
        canvas: gl.domElement,
        model,
        palette,
        quality,
        onReady: () => onStatusRef.current?.("ready"),
        onContextLost: () => onStatusRef.current?.("lost"),
        onContextRestored: () => onStatusRef.current?.("restored"),
      });
    } catch {
      onStatusRef.current?.("unavailable");
      return;
    }
    rendererRef.current = renderer;

    return () => {
      renderer?.dispose();
      rendererRef.current = null;
    };
  }, [gl, model, palette, quality]);

  useEffect(() => {
    if (!reducedMotion) return;
    // Reduced motion uses frameloop="never"; request one frame so the
    // static phase renders whenever the freeze time or viewport changes.
    invalidate();
  }, [reducedMotion, freezeTime, invalidate, size]);

  // Priority 1 disables R3F automatic rendering; this callback is the
  // sole renderer and must call into the DynamicRenderer every frame.
  useFrame((_, delta) => {
    const renderer = rendererRef.current;
    if (!renderer) return;
    renderer.resize(size.width, size.height);
    if (reducedMotion) {
      renderer.renderAt(freezeTime);
    } else {
      renderer.update(delta);
    }
  }, 1);

  return null;
}
