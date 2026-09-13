import { useCallback, useEffect, useReducer, useRef, useState } from "react";
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
  kind: "read" | "login" | "logout" | "context" | "context-recovery";
  controller: AbortController;
}

export interface ContextLease {
  signal: AbortSignal;
  cancel: () => void;
  valid: () => boolean;
  pendingInvalidation: () => boolean;
  recoverable: () => void;
  release: (verify?: boolean) => boolean;
}

export function useAuthSession() {
  const [state, setState] = useState<SessionState>({ status: "checking" });
  // Only the phase is mirrored for synchronous guards; identity lives solely in state.
  const phase = useRef<SessionState["status"]>("checking");
  const active = useRef<Operation | null>(null);
  const mounted = useRef(false);
  const pendingInvalidation = useRef(false);
  const revalidationTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const cycle = useRef(0);
  const [verification, queueVerification] = useReducer(
    (value: number) => value + 1,
    0,
  );
  const [mutationRevision, notifyMutation] = useReducer(
    (value: number) => value + 1,
    0,
  );

  const publish = useCallback((next: SessionState) => {
    phase.current = next.status;
    setState(next);
  }, []);

  const begin = useCallback((kind: Operation["kind"]): Operation => {
    clearTimeout(revalidationTimer.current);
    active.current?.controller.abort();
    if (kind !== "context") cycle.current += 1;
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

  const scheduleVerification = useCallback(() => {
    // Hide confirmed identity/context immediately; keep an anonymous login form mounted.
    if (phase.current !== "anonymous") publish({ status: "checking" });
    clearTimeout(revalidationTimer.current);
    revalidationTimer.current = setTimeout(() => {
      if (mounted.current) queueVerification();
    }, 75);
  }, [publish]);

  const finish = useCallback(
    (operation: Operation) => {
      if (active.current !== operation) return false;
      active.current = null;
      if (pendingInvalidation.current && mounted.current) {
        pendingInvalidation.current = false;
        scheduleVerification();
        return true;
      }
      return false;
    },
    [scheduleVerification],
  );

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
          if (isCurrent(operation) && phase.current !== "anonymous")
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
      clearTimeout(revalidationTimer.current);
      // Abort cannot undo a mutation already received by Django.
      active.current?.controller.abort();
      active.current = null;
    };
  }, [begin, runVerification, verification]);

  const verify = useCallback(() => {
    if (!mounted.current || (active.current && active.current.kind !== "read"))
      return;
    const operation = begin("read");
    publish({ status: "checking" });
    void runVerification(operation);
  }, [begin, publish, runVerification]);

  const invalidate = useCallback(() => {
    if (!mounted.current) return;
    if (
      active.current &&
      active.current.kind !== "read" &&
      active.current.kind !== "context-recovery"
    ) {
      pendingInvalidation.current = true;
      return;
    }
    active.current?.controller.abort();
    active.current = null;
    cycle.current += 1;
    scheduleVerification();
  }, [scheduleVerification]);

  const acquireContext = useCallback((): ContextLease | null => {
    if (!mounted.current || phase.current !== "authenticated" || active.current)
      return null;
    const operation = begin("context");
    return {
      signal: operation.controller.signal,
      cancel: () => operation.controller.abort(),
      valid: () => isCurrent(operation),
      pendingInvalidation: () => pendingInvalidation.current,
      recoverable: () => {
        if (isCurrent(operation)) operation.kind = "context-recovery";
      },
      release: (verify = false) => {
        if (!isCurrent(operation)) return false;
        if (verify) pendingInvalidation.current = true;
        return finish(operation);
      },
    };
  }, [begin, finish, isCurrent]);

  const identityId = state.status === "authenticated" ? state.user.id : null;
  const confirmIdentity = useCallback(
    async (signal: AbortSignal) => {
      const startedIn = cycle.current;
      const user = await getCurrentUser(signal);
      if (!mounted.current || signal.aborted || cycle.current !== startedIn)
        return false;
      if (user?.id !== identityId) {
        cycle.current += 1;
        active.current?.controller.abort();
        active.current = null;
        publishIdentity(user);
        return false;
      }
      publishIdentity(user);
      return true;
    },
    [identityId, publishIdentity],
  );

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
        if (posted && isCurrent(operation)) notifyMutation();
        finish(operation);
      }
    },
    [begin, finish, isCurrent, publish, publishIdentity, readSession],
  );

  const logout = useCallback(async () => {
    if (
      !mounted.current ||
      phase.current !== "authenticated" ||
      active.current?.kind === "context" ||
      active.current?.kind === "context-recovery"
    )
      return;
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
      if (posted && isCurrent(operation)) notifyMutation();
      finish(operation);
    }
  }, [begin, finish, isCurrent, publish, publishIdentity, readSession]);

  return {
    state,
    verify,
    login,
    logout,
    invalidate,
    acquireContext,
    confirmIdentity,
    mutationRevision,
  };
}

export type AuthSession = ReturnType<typeof useAuthSession>;
