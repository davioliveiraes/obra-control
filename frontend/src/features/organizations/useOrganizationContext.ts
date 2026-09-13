import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../shared/api/client";
import type { ApiFailure } from "../../shared/api/client";
import { getCsrfToken } from "../auth/api";
import type { AuthSession, ContextLease } from "../auth/useAuthSession";
import {
  clearOrganization,
  getCurrentOrganization,
  listOrganizations,
  selectOrganization,
} from "./api";
import type { AccessibleOrganization } from "./api";

interface ContextData {
  organizations: AccessibleOrganization[];
  current: AccessibleOrganization | null;
}

export type OrganizationState =
  | { status: "checking" | "changing" }
  | { status: "empty"; notice?: string }
  | {
      status: "choosing";
      organizations: AccessibleOrganization[];
      notice?: string;
    }
  | {
      status: "active";
      organizations: AccessibleOrganization[];
      current: AccessibleOrganization;
      notice?: string;
    }
  | { status: "error"; uncertain: boolean; failure?: ApiFailure };

interface Operation {
  signal: AbortSignal;
  cancel: () => void;
  lease?: ContextLease;
}

function ready(data: ContextData, notice?: string): OrganizationState {
  if (data.current)
    return { status: "active", ...data, current: data.current, notice };
  if (data.organizations.length)
    return { status: "choosing", organizations: data.organizations, notice };
  return { status: "empty", notice };
}

function http(error: unknown, status: number): boolean {
  return (
    error instanceof ApiError &&
    error.failure.kind === "http" &&
    error.failure.status === status
  );
}

// Its authenticated component is keyed by identity and unmounted during session
// verification/logout. No user or previous authentication cycle is stored here.
export function useOrganizationContext(
  session: AuthSession,
  notify: () => void,
) {
  const { acquireContext, confirmIdentity, verify } = session;
  const [snapshot, setSnapshot] = useState<{
    state: OrganizationState;
    revision: number;
  }>({ state: { status: "checking" }, revision: 0 });
  const revision = useRef(0);
  const mounted = useRef(false);
  const active = useRef<Operation | null>(null);
  const uncertainLease = useRef<ContextLease | null>(null);

  const publish = useCallback((state: OrganizationState) => {
    revision.current += 1;
    setSnapshot({ state, revision: revision.current });
  }, []);
  const current = useCallback(
    (operation: Operation) =>
      mounted.current &&
      active.current === operation &&
      !operation.signal.aborted &&
      (!operation.lease || operation.lease.valid()),
    [],
  );

  const readContext = useCallback(
    async (operation: Operation): Promise<ContextData | undefined> => {
      for (let attempt = 0; attempt < 2; attempt += 1) {
        if (!current(operation)) return;
        try {
          const [organizations, selected] = await Promise.all([
            listOrganizations(operation.signal),
            getCurrentOrganization(operation.signal),
          ]);
          if (!current(operation)) return;
          const accessible =
            selected && organizations.find((item) => item.id === selected.id);
          if (
            !selected ||
            (accessible &&
              accessible.name === selected.name &&
              accessible.role === selected.role)
          ) {
            return { organizations, current: selected };
          }
          if (attempt === 1) throw new ApiError({ kind: "invalid-response" });
        } catch (error) {
          if (attempt === 0 && http(error, 403) && current(operation)) {
            if (
              !(await confirmIdentity(operation.signal)) ||
              !current(operation)
            )
              return;
            continue;
          }
          throw error;
        }
      }
      throw new ApiError({ kind: "invalid-response" });
    },
    [confirmIdentity, current],
  );

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    const operation = {
      signal: controller.signal,
      cancel: () => controller.abort(),
    };
    active.current = operation;
    void readContext(operation)
      .then((data) => {
        if (data && current(operation)) publish(ready(data));
      })
      .catch((error) => {
        if (current(operation))
          publish({
            status: "error",
            uncertain: false,
            failure: error instanceof ApiError ? error.failure : undefined,
          });
      })
      .finally(() => {
        if (active.current === operation) active.current = null;
      });
    return () => {
      mounted.current = false;
      active.current?.cancel();
      active.current = null;
      uncertainLease.current?.cancel();
      uncertainLease.current = null;
    };
  }, [current, publish, readContext]);

  const mutate = useCallback(
    async (organizationId: number | null) => {
      const state = snapshot.state;
      if (
        !mounted.current ||
        active.current ||
        uncertainLease.current ||
        snapshot.revision !== revision.current ||
        (state.status !== "active" && state.status !== "choosing")
      )
        return;
      if (
        organizationId !== null &&
        !state.organizations.some((item) => item.id === organizationId)
      )
        return;
      if (organizationId === null && state.status !== "active") return;
      const lease = acquireContext();
      if (!lease) return;
      const operation = { signal: lease.signal, cancel: lease.cancel, lease };
      active.current = operation;
      publish({ status: "changing" });
      let posted = false;
      let accepted = false;
      try {
        const csrf = await getCsrfToken(operation.signal);
        if (!current(operation)) return;
        posted = true;
        if (organizationId === null)
          await clearOrganization(csrf, operation.signal);
        else await selectOrganization(organizationId, csrf, operation.signal);
        if (!current(operation)) return;
        accepted = true;
        const data = await readContext(operation);
        if (!data || !current(operation)) return;
        const changedElsewhere = (data.current?.id ?? null) !== organizationId;
        // A queued tab/focus event must verify identity before another context is published.
        if (!lease.release())
          publish(
            ready(
              data,
              changedElsewhere
                ? "O contexto atual difere da alteração solicitada. Foi apresentada a situação confirmada pela API."
                : undefined,
            ),
          );
      } catch (error) {
        if (!current(operation)) return;
        if (posted && !accepted && http(error, 403)) {
          try {
            if (
              !(await confirmIdentity(operation.signal)) ||
              !current(operation)
            )
              return;
            const data = await readContext(operation);
            if (data && current(operation)) {
              if (!lease.release())
                publish(
                  ready(
                    data,
                    "A alteração foi recusada. O contexto atual foi verificado novamente.",
                  ),
                );
              return;
            }
          } catch {
            /* Keep the original HTTP rejection; do not replace it with anonymity. */
          }
        }
        if (!current(operation)) return;
        const uncertain =
          posted && (accepted || (!http(error, 400) && !http(error, 403)));
        if (uncertain && !lease.pendingInvalidation()) {
          lease.recoverable();
          uncertainLease.current = lease;
          publish({
            status: "error",
            uncertain: true,
            failure: error instanceof ApiError ? error.failure : undefined,
          });
        } else if (!lease.release()) {
          publish({
            status: "error",
            uncertain,
            failure: error instanceof ApiError ? error.failure : undefined,
          });
        }
      } finally {
        if (posted && mounted.current) notify();
        if (active.current === operation) active.current = null;
        // A changed/anonymous identity already invalidates the lease in useAuthSession.
        if (lease.valid() && uncertainLease.current !== lease) lease.release();
      }
    },
    [
      acquireContext,
      confirmIdentity,
      current,
      notify,
      publish,
      readContext,
      snapshot,
    ],
  );

  const recover = useCallback(() => {
    if (!mounted.current || active.current) return;
    if (uncertainLease.current) {
      const lease = uncertainLease.current;
      uncertainLease.current = null;
      lease.release(true);
    } else verify();
  }, [verify]);

  return {
    ...snapshot,
    select: (id: number) => mutate(id),
    clear: () => mutate(null),
    recover,
    mutationBlocked:
      snapshot.state.status === "changing" ||
      (snapshot.state.status === "error" && snapshot.state.uncertain),
  };
}
