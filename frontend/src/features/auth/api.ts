import { ApiError, request } from "../../shared/api/client";

export interface UserIdentity {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface LoginProblem {
  message: string;
  fields?: Partial<Record<keyof LoginCredentials, string>>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export async function getCsrfToken(signal?: AbortSignal): Promise<string> {
  const data = await request("/api/v1/auth/csrf/", {
    signal,
    cache: "no-store",
    expectedStatus: 200,
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
    data = await request("/api/v1/auth/me/", {
      signal,
      cache: "no-store",
      expectedStatus: 200,
    });
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
  return validateIdentity(data);
}

function validateIdentity(data: unknown): UserIdentity {
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

export async function login(
  credentials: LoginCredentials,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<UserIdentity> {
  const data = await request("/api/v1/auth/login/", {
    method: "POST",
    json: { email: credentials.email, password: credentials.password },
    csrfToken,
    signal,
    cache: "no-store",
    expectedStatus: 200,
  });
  return validateIdentity(data);
}

export async function logout(
  csrfToken: string,
  signal?: AbortSignal,
): Promise<void> {
  await request("/api/v1/auth/logout/", {
    method: "POST",
    csrfToken,
    signal,
    cache: "no-store",
    expectedStatus: 204,
  });
}

// These are known rejections of LoginView, not a global interpretation of HTTP errors.
export function getLoginRejection(error: unknown): LoginProblem | undefined {
  if (!(error instanceof ApiError) || error.failure.kind !== "http") return;
  const { status, data } = error.failure;
  if (status === 403) {
    return {
      message: "A entrada foi recusada pela proteção CSRF. Tente novamente.",
    };
  }
  if (status !== 400 || !isRecord(data)) return;
  const keys = Object.keys(data);
  if (keys.length === 1 && data.detail === "Credenciais inválidas.") {
    return { message: "E-mail ou senha inválidos" };
  }
  if (
    keys.length > 0 &&
    keys.every(
      (key) =>
        (key === "email" || key === "password") &&
        Array.isArray(data[key]) &&
        data[key].length > 0 &&
        data[key].every((message: unknown) => typeof message === "string"),
    )
  ) {
    // Never render arbitrary server messages (which may contain sensitive data).
    const fields: LoginProblem["fields"] = {};
    if ("email" in data) fields.email = "Confira o e-mail informado.";
    if ("password" in data) fields.password = "Confira a senha informada.";
    return { message: "Confira os campos indicados.", fields };
  }
}
