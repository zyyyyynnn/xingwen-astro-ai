import { Separator, type SeparatorProps } from "react-resizable-panels";

/**
 * Governed resizable panel handle surface for product code.
 *
 * Pointer drag, keyboard adjustment and ARIA separator semantics are owned
 * by react-resizable-panels. Product code keeps importing this surface from
 * @xingwen/ui so the dependency does not leak across application boundaries.
 * See ../component-sources.json for the reviewed source and consumers.
 */
export const ResizableHandle = Separator;

export type ResizableHandleProps = SeparatorProps;
