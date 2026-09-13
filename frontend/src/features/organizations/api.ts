import { ApiError, request } from "../../shared/api/client";

export type OrganizationRole = "owner" | "admin" | "member";

export interface AccessibleOrganization {
  id: number;
  name: string;
  role: OrganizationRole;
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function organization(value: unknown): AccessibleOrganization {
  if (
    !record(value) ||
    typeof value.id !== "number" ||
    !Number.isSafeInteger(value.id) ||
    value.id <= 0 ||
    typeof value.name !== "string" ||
    !value.name.trim()
  ) {
    throw new ApiError({ kind: "invalid-response" });
  }
  const role = value.role;
  if (role !== "owner" && role !== "admin" && role !== "member") {
    throw new ApiError({ kind: "invalid-response" });
  }
  return { id: value.id, name: value.name, role };
}

export async function listOrganizations(
  signal?: AbortSignal,
): Promise<AccessibleOrganization[]> {
  const data = await request("/api/v1/organizations/", {
    signal,
    cache: "no-store",
    expectedStatus: 200,
  });
  if (!Array.isArray(data)) throw new ApiError({ kind: "invalid-response" });
  const organizations = data.map(organization);
  if (
    new Set(organizations.map((item) => item.id)).size !== organizations.length
  ) {
    throw new ApiError({ kind: "invalid-response" });
  }
  return organizations;
}

export async function getCurrentOrganization(
  signal?: AbortSignal,
): Promise<AccessibleOrganization | null> {
  try {
    return organization(
      await request("/api/v1/organizations/current/", {
        signal,
        cache: "no-store",
        expectedStatus: 200,
      }),
    );
  } catch (error) {
    if (error instanceof ApiError && error.failure.kind === "http") {
      const { status, data } = error.failure;
      if (
        status === 404 &&
        record(data) &&
        Object.keys(data).length === 1 &&
        data.detail === "Nenhuma organização selecionada."
      ) {
        return null;
      }
    }
    throw error;
  }
}

export async function selectOrganization(
  organization_id: number,
  csrfToken: string,
  signal?: AbortSignal,
): Promise<AccessibleOrganization> {
  if (!Number.isSafeInteger(organization_id) || organization_id <= 0) {
    throw new ApiError({ kind: "invalid-request" });
  }
  const selected = organization(
    await request("/api/v1/organizations/current/", {
      method: "PUT",
      json: { organization_id },
      csrfToken,
      signal,
      cache: "no-store",
      expectedStatus: 200,
    }),
  );
  if (selected.id !== organization_id) {
    throw new ApiError({ kind: "invalid-response" });
  }
  return selected;
}

export async function clearOrganization(
  csrfToken: string,
  signal?: AbortSignal,
): Promise<void> {
  await request("/api/v1/organizations/current/", {
    method: "DELETE",
    csrfToken,
    signal,
    cache: "no-store",
    expectedStatus: 204,
  });
}
