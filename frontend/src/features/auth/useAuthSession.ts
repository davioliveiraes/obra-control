import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../shared/api/client";
import {
  getCsrfToken,
  getCurrentUser,
  getLoginRejection,
  login as postLogin,
  logout as postLogout,
} from "./api";
import type { LoginCredentials, LoginProblem, UserIdentity } from "./api";

export type SessionState =
  | { status: "checking" }
  | { status: "signing-in" }
  | { status: "signing-out" }
  | { status: "authenticated"; user: UserIdentity; logoutUnconfirmed?: true }
  | { status: "anonymous"; problem?: LoginProblem }
  | {
      status: "error";
      reason:
        | "read"
        | "login-preparation"
        | "logout-preparation"
        | "login-unconfirmed"
        | "logout-unconfirmed"
        | "logout-rejected";
    };

interface Operation {
  kind: "read" | "login" | "logout";
  controller: AbortController;
}

export function useAuthSession() {
  const [state, setState] = useState<SessionState>({ status: "checking" });
  // Only the phase is mirrored for synchronous guards; identity lives solely in state.
  const phase = useRef<SessionState["status"]>("checking");
  const active = useRef<Operation | null>(null);
  const mounted = useRef(false);

  const publish = useCallback((next: SessionState) => {
    phase.current = next.status;
    setState(next);
  }, []);

  const begin = useCallback((kind: Operation["kind"]): Operation => {
    active.current?.controller.abort();
    const operation = { kind, controller: new AbortController() };
    active.current = operation;
    return operation;
  }, []);

  const isCurrent = useCallback(
    (operation: Operation) =>
      mounted.current &&
      active.current === operation &&
      !operation.controller.signal.aborted,
    [],
  );

  const finish = useCallback((operation: Operation) => {
    if (active.current === operation) active.current = null;
  }, []);

  const readSession = useCallback(
    async (operation: Operation) => {
      const signal = operation.controller.signal;
      await getCsrfToken(signal);
      if (!isCurrent(operation)) return;
      const user = await getCurrentUser(signal);
      if (!isCurrent(operation)) return;
      return user;
    },
    [isCurrent],
  );

  const publishIdentity = useCallback(
    (user: UserIdentity | null, afterLogout = false) => {
      if (user) {
        publish(
          afterLogout
            ? { status: "authenticated", user, logoutUnconfirmed: true }
            : { status: "authenticated", user },
        );
      } else {
        publish({ status: "anonymous" });
      }
    },
    [publish],
  );

  const runVerification = useCallback(
    (operation: Operation) =>
      readSession(operation)
        .then((user) => {
          if (isCurrent(operation) && user !== undefined) publishIdentity(user);
        })
        .catch(() => {
          if (isCurrent(operation))
            publish({ status: "error", reason: "read" });
        })
        .finally(() => finish(operation)),
    [finish, isCurrent, publish, publishIdentity, readSession],
  );

  useEffect(() => {
    mounted.current = true;
    const operation = begin("read");
    void runVerification(operation);
    return () => {
      mounted.current = false;
      // Abort cannot undo a mutation already received by Django.
      active.current?.controller.abort();
      active.current = null;
    };
  }, [begin, runVerification]);

  const verify = useCallback(() => {
    if (!mounted.current || (active.current && active.current.kind !== "read"))
      return;
    const operation = begin("read");
    publish({ status: "checking" });
    void runVerification(operation);
  }, [begin, publish, runVerification]);

  const login = useCallback(
    async (credentials: LoginCredentials) => {
      if (!mounted.current || phase.current !== "anonymous") return;
      const operation = begin("login");
      publish({ status: "signing-in" });
      const signal = operation.controller.signal;
      let posted = false;
      let accepted = false;
      try {
        const csrfToken = await getCsrfToken(signal);
        if (!isCurrent(operation)) return;
        posted = true;
        await postLogin(credentials, csrfToken, signal);
        if (!isCurrent(operation)) return;
        accepted = true;
        publish({ status: "checking" });
        // Login rotates CSRF. Only a fresh /me response publishes identity.
        const user = await readSession(operation);
        if (isCurrent(operation) && user !== undefined) publishIdentity(user);
      } catch (error) {
        if (!isCurrent(operation)) return;
        const problem =
          posted && !accepted ? getLoginRejection(error) : undefined;
        if (problem) publish({ status: "anonymous", problem });
        else
          publish({
            status: "error",
            reason: posted ? "login-unconfirmed" : "login-preparation",
          });
      } finally {
        finish(operation);
      }
    },
    [begin, finish, isCurrent, publish, publishIdentity, readSession],
  );

  const logout = useCallback(async () => {
    if (!mounted.current || phase.current !== "authenticated") return;
    const operation = begin("logout");
    // Hide the previous identity for the entire operation; never restore a cached user.
    publish({ status: "signing-out" });
    const signal = operation.controller.signal;
    let posted = false;
    let accepted = false;
    try {
      const csrfToken = await getCsrfToken(signal);
      if (!isCurrent(operation)) return;
      posted = true;
      await postLogout(csrfToken, signal);
      if (!isCurrent(operation)) return;
      accepted = true;
      publish({ status: "checking" });
      const user = await readSession(operation);
      if (isCurrent(operation) && user !== undefined)
        publishIdentity(user, true);
    } catch (error) {
      if (!isCurrent(operation)) return;
      const rejected =
        !accepted &&
        error instanceof ApiError &&
        error.failure.kind === "http" &&
        error.failure.status === 403;
      publish({
        status: "error",
        reason: !posted
          ? "logout-preparation"
          : rejected
            ? "logout-rejected"
            : "logout-unconfirmed",
      });
    } finally {
      finish(operation);
    }
  }, [begin, finish, isCurrent, publish, publishIdentity, readSession]);

  return { state, verify, login, logout };
}
