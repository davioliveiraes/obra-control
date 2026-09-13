import { beforeEach, expect, test, vi } from "vitest";
import {
  clearOrganization,
  getCurrentOrganization,
  listOrganizations,
  selectOrganization,
} from "./api";
import { csrfToken, jsonResponse } from "../../test/apiFixtures";
import {
  firstOrganization as first,
  secondOrganization as second,
  noOrganization,
} from "../../test/organizationFixtures";

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

test("lista plana preserva ordem e papel da Membership; leituras não usam cache ou CSRF", async () => {
  fetchMock
    .mockResolvedValueOnce(jsonResponse([first, second]))
    .mockResolvedValueOnce(jsonResponse(first));
  await expect(listOrganizations()).resolves.toEqual([first, second]);
  await expect(getCurrentOrganization()).resolves.toEqual(first);
  for (const [, options] of fetchMock.mock.calls) {
    expect(options?.cache).toBe("no-store");
    expect(options?.credentials).toBe("same-origin");
    expect(new Headers(options?.headers).has("X-CSRFToken")).toBe(false);
  }
});

test("lista vazia é válida", async () => {
  fetchMock.mockResolvedValue(jsonResponse([]));
  await expect(listOrganizations()).resolves.toEqual([]);
});

test.each([
  { data: null },
  { data: {} },
  { data: { results: [first], count: 1, next: null, previous: null } },
  { data: [first, first] },
  { data: [null] },
  { data: [{ ...first, id: 0 }] },
  { data: [{ ...first, role: "OWNER" }] },
  { data: [{ ...first, name: "" }] },
])("rejeita envelope/lista inválidos: %j", async ({ data }) => {
  fetchMock.mockResolvedValue(jsonResponse(data));
  await expect(listOrganizations()).rejects.toMatchObject({
    failure: { kind: "invalid-response" },
  });
});

test.each([
  { data: null },
  { data: {} },
  { data: [] },
  { data: { ...first, id: "11" } },
  { data: { ...first, id: 1.1 } },
  { data: { ...first, id: Number.MAX_SAFE_INTEGER + 1 } },
  { data: { ...first, name: null } },
  { data: { ...first, role: "unknown" } },
  { data: { ...first, role: 1 } },
])("rejeita current inválido: %j", async ({ data }) => {
  fetchMock.mockResolvedValue(jsonResponse(data));
  await expect(getCurrentOrganization()).rejects.toMatchObject({
    failure: { kind: "invalid-response" },
  });
});

test("somente GET current com o 404 exato representa ausência", async () => {
  fetchMock.mockImplementation(async () => jsonResponse(noOrganization, 404));
  await expect(getCurrentOrganization()).resolves.toBeNull();
  await expect(listOrganizations()).rejects.toMatchObject({
    failure: { kind: "http", status: 404, data: noOrganization },
  });
});

test.each([
  [404, { detail: "Não encontrado." }],
  [404, { ...noOrganization, extra: true }],
  [403, noOrganization],
  [500, noOrganization],
])("preserva HTTP %s fora do contrato exato", async (status, data) => {
  fetchMock.mockResolvedValue(jsonResponse(data, Number(status)));
  await expect(getCurrentOrganization()).rejects.toMatchObject({
    failure: { kind: "http", status, data },
  });
});

test("PUT envia somente organization_id, cookies e CSRF explícito", async () => {
  fetchMock.mockResolvedValue(jsonResponse(second));
  await expect(selectOrganization(second.id, csrfToken)).resolves.toEqual(
    second,
  );
  const [path, options] = fetchMock.mock.calls[0];
  expect(path).toBe("/api/v1/organizations/current/");
  expect(options?.method).toBe("PUT");
  expect(options?.body).toBe(JSON.stringify({ organization_id: second.id }));
  expect(options?.credentials).toBe("same-origin");
  expect(new Headers(options?.headers).get("X-CSRFToken")).toBe(csrfToken);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test.each([0, -1, 1.2, Number.MAX_SAFE_INTEGER + 1])(
  "ID inválido %s não é enviado",
  async (id) => {
    await expect(selectOrganization(id, csrfToken)).rejects.toMatchObject({
      failure: { kind: "invalid-request" },
    });
    expect(fetchMock).not.toHaveBeenCalled();
  },
);

test("PUT exige representação válida da organização solicitada", async () => {
  fetchMock
    .mockResolvedValueOnce(jsonResponse({}))
    .mockResolvedValueOnce(jsonResponse(second));
  await expect(selectOrganization(first.id, csrfToken)).rejects.toMatchObject({
    failure: { kind: "invalid-response" },
  });
  await expect(selectOrganization(first.id, csrfToken)).rejects.toMatchObject({
    failure: { kind: "invalid-response" },
  });
});

test("DELETE limpa current com 204 vazio, sem excluir entidade ou enviar corpo", async () => {
  fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
  await expect(clearOrganization(csrfToken)).resolves.toBeUndefined();
  const [path, options] = fetchMock.mock.calls[0];
  expect(path).toBe("/api/v1/organizations/current/");
  expect(options?.method).toBe("DELETE");
  expect(options?.body).toBeUndefined();
  expect(new Headers(options?.headers).get("X-CSRFToken")).toBe(csrfToken);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test.each([201, 202, 204])(
  "PUT não aceita o status inesperado %s",
  async (status) => {
    fetchMock.mockResolvedValue(
      status === 204
        ? new Response(null, { status })
        : jsonResponse(first, status),
    );
    await expect(selectOrganization(first.id, csrfToken)).rejects.toMatchObject(
      { failure: { kind: "invalid-response" } },
    );
  },
);

test.each([200, 201, 202])(
  "DELETE não aceita o status inesperado %s",
  async (status) => {
    fetchMock.mockResolvedValue(jsonResponse({}, status));
    await expect(clearOrganization(csrfToken)).rejects.toMatchObject({
      failure: { kind: "invalid-response" },
    });
  },
);

test.each(["select", "clear"] as const)(
  "%s sem CSRF não é enviado",
  async (action) => {
    await expect(
      action === "select"
        ? selectOrganization(first.id, "")
        : clearOrganization(""),
    ).rejects.toMatchObject({ failure: { kind: "invalid-request" } });
    expect(fetchMock).not.toHaveBeenCalled();
  },
);

test.each([403, 500])(
  "falha HTTP %s de mutação preserva status/payload sem retry",
  async (status) => {
    const data = { detail: "Organização indisponível." };
    fetchMock.mockResolvedValue(jsonResponse(data, status));
    await expect(selectOrganization(first.id, csrfToken)).rejects.toMatchObject(
      { failure: { kind: "http", status, data } },
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  },
);
