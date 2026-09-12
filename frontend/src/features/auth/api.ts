import { ApiError, request } from "../../shared/api/client";

export interface UserIdentity {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export async function getCsrfToken(signal?: AbortSignal): Promise<string> {
  const data = await request("/api/v1/auth/csrf/", {
    signal,
    cache: "no-store",
  });
  if (
    !isRecord(data) ||
    typeof data.csrfToken !== "string" ||
    !/^[a-zA-Z0-9]+$/.test(data.csrfToken)
  ) {
    throw new ApiError({ kind: "invalid-response" });
  }
  return data.csrfToken;
}

export async function getCurrentUser(
  signal?: AbortSignal,
): Promise<UserIdentity | null> {
  let data: unknown;
  try {
    data = await request("/api/v1/auth/me/", { signal, cache: "no-store" });
  } catch (error) {
    if (error instanceof ApiError && error.failure.kind === "http") {
      const { status, data: payload } = error.failure;
      // Exact current pt-br contract of MeView + DRF NotAuthenticated.
      // There is no machine-readable code, nor a distinction between missing/expired sessions.
      if (
        status === 403 &&
        isRecord(payload) &&
        Object.keys(payload).length === 1 &&
        payload.detail ===
          "As credenciais de autenticação não foram fornecidas."
      ) {
        return null;
      }
    }
    throw error;
  }
  if (
    !isRecord(data) ||
    typeof data.id !== "number" ||
    !Number.isSafeInteger(data.id) ||
    data.id <= 0 ||
    typeof data.email !== "string" ||
    !data.email.trim() ||
    typeof data.first_name !== "string" ||
    typeof data.last_name !== "string"
  ) {
    throw new ApiError({ kind: "invalid-response" });
  }
  return {
    id: data.id,
    email: data.email,
    first_name: data.first_name,
    last_name: data.last_name,
  };
}
