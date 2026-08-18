import { Panel, type PanelProps } from "react-resizable-panels";

/**
 * Governed resizable panel surface for product code.
 *
 * Sizing constraints and resize mechanics are owned by
 * react-resizable-panels; product sizing stays declarative. Product code
 * keeps importing this surface from @xingwen/ui so the dependency does not
 * leak across application boundaries.
 * See ../component-sources.json for the reviewed source and consumers.
 */
export const ResizablePanel = Panel;

export type ResizablePanelProps = PanelProps;
