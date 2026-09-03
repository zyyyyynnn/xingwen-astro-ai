import { type RefObject, useCallback, useRef, useState } from "react";

/** OpenHands bottom-following mechanic: manual upward scroll pauses following. */
export function useScrollToBottom(
  scrollRef: RefObject<HTMLDivElement | null>,
  threadItemCount = 0,
) {
  const [autoScroll, setAutoScroll] = useState(true);
  const [hitBottom, setHitBottom] = useState(true);
  // Item count acknowledged the last time the reader reached the bottom;
  // items published after that point are counted as pending progress while
  // the reader stays scrolled up.
  const [acknowledgedCount, setAcknowledgedCount] = useState(threadItemCount);
  const previousScrollTop = useRef(0);
  const pendingNewCount = hitBottom
    ? 0
    : Math.max(0, threadItemCount - acknowledgedCount);

  const onChatBodyScroll = useCallback(
    (element: HTMLElement) => {
      const atBottom =
        element.scrollTop + element.clientHeight >= element.scrollHeight - 20;
      setHitBottom(atBottom);
      if (element.scrollTop < previousScrollTop.current) setAutoScroll(false);
      if (atBottom) {
        setAutoScroll(true);
        setAcknowledgedCount(threadItemCount);
      }
      previousScrollTop.current = element.scrollTop;
    },
    [threadItemCount],
  );

  const scrollDomToBottom = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;
    requestAnimationFrame(() => {
      setAutoScroll(true);
      setHitBottom(true);
      setAcknowledgedCount(threadItemCount);
      element.scrollTop = element.scrollHeight;
    });
  }, [scrollRef, threadItemCount]);

  return {
    autoScroll,
    hitBottom,
    onChatBodyScroll,
    pendingNewCount,
    scrollDomToBottom,
  };
}
