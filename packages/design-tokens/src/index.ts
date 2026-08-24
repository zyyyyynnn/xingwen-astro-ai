/**
 * Geometry consumed by the governed Graph layout engine. XYFlow and Dagre use
 * CSS-pixel coordinate systems, so these semantic values keep those decisions
 * out of product components while matching the workspace CSS tokens.
 */
export const workspaceGraphGeometry = Object.freeze({
  nodeInlineSize: 224,
  nodeBlockSize: 72,
  nodeSeparation: 48,
  rankSeparation: 96,
  focusPadding: 0.24,
});
