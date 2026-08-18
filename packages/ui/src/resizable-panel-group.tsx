import { Group, type GroupProps } from "react-resizable-panels";

/**
 * Governed resizable panel-group surface for product code.
 *
 * Layout orchestration, pointer/keyboard resizing and min/max constraint
 * mechanics are owned by react-resizable-panels. Product code keeps
 * importing this surface from @xingwen/ui so the dependency does not leak
 * across application boundaries.
 * See ../component-sources.json for the reviewed source and consumers.
 */
export const ResizablePanelGroup = Group;

export type ResizablePanelGroupProps = GroupProps;
