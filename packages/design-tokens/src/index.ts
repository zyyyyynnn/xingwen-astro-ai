/**
 * Geometry consumed by the governed Graph layout engine. XYFlow and Dagre use
 * CSS-pixel coordinate systems, so these semantic values keep those decisions
 * out of product components while matching the workspace CSS tokens.
 */
export const workspaceGraphGeometry = Object.freeze({
  nodeInlineSize: "--workspace-result-node-inline-size",
  nodeBlockSize: "--workspace-result-node-block-size",
  nodeSeparation: "--workspace-result-node-separation",
  rankSeparation: "--workspace-result-rank-separation",
  focusPadding: "--workspace-result-graph-focus-padding",
});
