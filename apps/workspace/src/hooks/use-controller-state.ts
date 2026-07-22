import { useSyncExternalStore } from "react";

interface SubscribableController<TState> {
  getState(): TState;
  subscribe(listener: (state: TState) => void): () => void;
}

export function useControllerState<TState>(
  controller: SubscribableController<TState>,
): TState {
  return useSyncExternalStore(
    (notify) => controller.subscribe(() => notify()),
    () => controller.getState(),
    () => controller.getState(),
  );
}
