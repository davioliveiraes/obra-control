import { useCallback, useEffect, useRef, useState } from "react";
import { getCsrfToken, getCurrentUser } from "./api";
import type { UserIdentity } from "./api";

export type SessionState =
  | { status: "checking" }
  | { status: "authenticated"; user: UserIdentity }
  | { status: "anonymous" }
  | { status: "error" };

export function useSessionBootstrap() {
  const [state, setState] = useState<SessionState>({ status: "checking" });
  const [attempt, setAttempt] = useState(0);
  const generation = useRef(0);
  const currentController = useRef<AbortController | null>(null);

  useEffect(() => {
    const id = ++generation.current;
    const controller = new AbortController();
    currentController.current = controller;
    const isCurrent = () =>
      generation.current === id && !controller.signal.aborted;

    const bootstrap = async () => {
      try {
        await getCsrfToken(controller.signal);
        if (!isCurrent()) return;
        const user = await getCurrentUser(controller.signal);
        if (isCurrent()) {
          setState(
            user ? { status: "authenticated", user } : { status: "anonymous" },
          );
        }
      } catch {
        if (isCurrent()) setState({ status: "error" });
      }
    };
    void bootstrap();

    return () => {
      controller.abort();
      if (currentController.current === controller)
        currentController.current = null;
    };
  }, [attempt]);

  const retry = useCallback(() => {
    ++generation.current;
    currentController.current?.abort();
    setState({ status: "checking" });
    setAttempt((value) => value + 1);
  }, []);

  return { state, retry };
}
