import type { ContentHash } from "@xingwen/domain";
import { Spinner } from "@xingwen/ui";
import { useEffect, useRef, useState } from "react";

import { openWwtSession, type WwtSpec } from "./wwt-session";

interface WwtViewportProps {
  readonly spec: WwtSpec;
  readonly loadContent: (contentHash: ContentHash) => Promise<ArrayBuffer>;
}

export function WwtViewport({ spec, loadContent }: WwtViewportProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("正在初始化 WorldWide Telescope");

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let active = true;
    const session = openWwtSession(host);
    setState("loading");
    setMessage("正在初始化 WorldWide Telescope");
    void session
      .render(spec, {
        loadContent,
        onProgress: (nextMessage) => {
          if (active) setMessage(nextMessage);
        },
      })
      .then(() => {
        if (active) setState("ready");
      })
      .catch((error: unknown) => {
        if (!active) return;
        setState("error");
        setMessage(
          error instanceof Error ? error.message : "WWT 场景初始化失败",
        );
      });
    return () => {
      active = false;
      session.close();
    };
  }, [loadContent, spec]);

  return (
    <figure className="wwt-viewport" aria-busy={state === "loading"}>
      <div ref={hostRef} className="wwt-viewport__canvas" />
      {state !== "ready" ? (
        <figcaption data-state={state}>
          {state === "loading" ? <Spinner aria-hidden="true" /> : null}
          <span>{message}</span>
        </figcaption>
      ) : null}
    </figure>
  );
}
