import { type RefObject, useCallback, useRef, useState } from "react";

/** OpenHands bottom-following mechanic: manual upward scroll pauses following. */
export function useScrollToBottom(scrollRef: RefObject<HTMLDivElement | null>) {
  const [autoScroll, setAutoScroll] = useState(true);
  const [hitBottom, setHitBottom] = useState(true);
  const previousScrollTop = useRef(0);

  const onChatBodyScroll = useCallback((element: HTMLElement) => {
    const atBottom =
      element.scrollTop + element.clientHeight >= element.scrollHeight - 20;
    setHitBottom(atBottom);
    if (element.scrollTop < previousScrollTop.current) setAutoScroll(false);
    if (atBottom) setAutoScroll(true);
    previousScrollTop.current = element.scrollTop;
  }, []);

  const scrollDomToBottom = useCallback(() => {
    const element = scrollRef.current;
    if (!element) return;
    requestAnimationFrame(() => {
      setAutoScroll(true);
      setHitBottom(true);
      element.scrollTop = element.scrollHeight;
    });
  }, [scrollRef]);

  return { autoScroll, hitBottom, onChatBodyScroll, scrollDomToBottom };
}
