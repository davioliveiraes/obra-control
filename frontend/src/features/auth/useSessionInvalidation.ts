import { useCallback, useEffect, useEffectEvent, useRef } from "react";

const CHANNEL = "obracontrol-session-context-v1";

function isInvalidation(data: unknown): boolean {
  return (
    typeof data === "object" &&
    data !== null &&
    !Array.isArray(data) &&
    Object.keys(data).sort().join(",") === "type,version" &&
    "type" in data &&
    data.type === "invalidate" &&
    "version" in data &&
    data.version === 1
  );
}

export function useSessionInvalidation(
  invalidate: () => void,
  mutationRevision: number,
) {
  const channel = useRef<BroadcastChannel | null>(null);
  const receive = useEffectEvent(invalidate);

  useEffect(() => {
    const onFocus = () => receive();
    const onVisible = () => {
      if (document.visibilityState === "visible") receive();
    };
    const onMessage = (event: MessageEvent<unknown>) => {
      if (isInvalidation(event.data)) receive();
    };
    try {
      if (typeof BroadcastChannel !== "undefined") {
        channel.current = new BroadcastChannel(CHANNEL);
        channel.current.addEventListener("message", onMessage);
      }
    } catch {
      channel.current = null;
    }
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisible);
      channel.current?.removeEventListener("message", onMessage);
      channel.current?.close();
      channel.current = null;
    };
  }, []);

  const notify = useCallback(() => {
    try {
      channel.current?.postMessage({ type: "invalidate", version: 1 });
    } catch {
      /* Focus/visibility remain available if the channel is unavailable. */
    }
  }, []);

  useEffect(() => {
    if (mutationRevision > 0) notify();
  }, [mutationRevision, notify]);

  return notify;
}
