import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

interface SidebarState {
  collapsed: boolean;
  /** True while a narrow viewport forces the icon rail; user preference resumes on the way back up. */
  autoCollapsed: boolean;
  toggleCollapsed: () => void;
  setAutoCollapsed: (autoCollapsed: boolean) => void;
}

export const useSidebarStore = create<SidebarState>()(
  persist(
    (set) => ({
      collapsed: false,
      autoCollapsed: false,
      toggleCollapsed: () =>
        set((state) => ({
          collapsed: !state.collapsed,
          autoCollapsed: false,
        })),
      setAutoCollapsed: (narrow) => {
        // Entering narrow collapses the rail; leaving narrow restores the
        // user's own preference rather than the auto state.
        set((state) =>
          narrow
            ? { collapsed: true, autoCollapsed: true }
            : {
                autoCollapsed: false,
                collapsed: state.autoCollapsed ? false : state.collapsed,
              },
        );
      },
    }),
    {
      name: "xingwen-agent-sidebar",
      storage: createJSONStorage(() => localStorage),
      partialize: ({ collapsed }) => ({ collapsed }),
    },
  ),
);

/** Viewport below which the sidebar collapses to its icon rail (spec: ~1100–1150px). */
export const SIDEBAR_NARROW_MEDIA_QUERY = "(max-width: 1150px)";

export function subscribeSidebarViewport(
  onChange: (narrow: boolean) => void,
): () => void {
  if (typeof window === "undefined" || !window.matchMedia) {
    return () => {};
  }
  const media = window.matchMedia(SIDEBAR_NARROW_MEDIA_QUERY);
  onChange(media.matches);
  const listener = (event: MediaQueryListEvent) => onChange(event.matches);
  media.addEventListener("change", listener);
  return () => media.removeEventListener("change", listener);
}
