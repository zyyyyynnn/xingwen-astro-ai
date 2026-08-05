import { useEffect, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import {
  createDynamicRenderer,
  type DynamicRenderer,
  type Quality,
  type ResearchSceneModel,
  type ScenePalette,
} from "@xingwen/visual-engine";

export type TransitStatus = "unavailable" | "lost" | "restored";

interface TransitSceneProps {
  model: ResearchSceneModel;
  palette: ScenePalette;
  quality: Quality;
  reducedMotion: boolean;
  freezeTime: number;
  onStatus?: (status: TransitStatus) => void;
}

/**
 * R3F Site Adapter — owns the WebGL canvas lifecycle (via the Canvas
 * from @react-three/fiber) and drives @xingwen/visual-engine's
 * DynamicRenderer: geometry is created once, then every frame the
 * renderer is resized to the current CSS size and advanced. Reduced
 * motion renders a single static phase instead of a continuous loop.
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
      });
    } catch {
      onStatusRef.current?.("unavailable");
      return;
    }
    rendererRef.current = renderer;

    const canvas = gl.domElement;
    const handleLost = (event: Event): void => {
      event.preventDefault();
      onStatusRef.current?.("lost");
    };
    const handleRestored = (): void => {
      onStatusRef.current?.("restored");
    };
    canvas.addEventListener("webglcontextlost", handleLost, false);
    canvas.addEventListener("webglcontextrestored", handleRestored, false);

    return () => {
      canvas.removeEventListener("webglcontextlost", handleLost, false);
      canvas.removeEventListener("webglcontextrestored", handleRestored, false);
      renderer?.dispose();
      rendererRef.current = null;
    };
  }, [gl, model, palette, quality]);

  useEffect(() => {
    if (!reducedMotion) return;
    const renderer = rendererRef.current;
    if (!renderer) return;
    renderer.resize(size.width, size.height);
    renderer.renderAt(freezeTime);
    invalidate();
  }, [reducedMotion, freezeTime, invalidate, size]);

  useFrame((_, delta) => {
    const renderer = rendererRef.current;
    if (!renderer) return;
    renderer.resize(size.width, size.height);
    if (!reducedMotion) {
      renderer.update(delta);
    }
  });

  return null;
}
