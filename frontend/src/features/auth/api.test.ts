import { beforeEach, expect, test, vi } from "vitest";
import { getCsrfToken, getCurrentUser } from "./api";
import {
  anonymousPayload,
  csrfToken,
  jsonResponse,
  user,
} from "../../test/apiFixtures";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

test("lê CSRF e identidade com no-store, sem renomear campos nem persistir dados", async () => {
  const local = vi.spyOn(Storage.prototype, "setItem");
  fetchMock
    .mockResolvedValueOnce(jsonResponse({ csrfToken }))
    .mockResolvedValueOnce(jsonResponse(user));
  await expect(getCsrfToken()).resolves.toBe(csrfToken);
  await expect(getCurrentUser()).resolves.toEqual(user);
  expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
    "/api/v1/auth/csrf/",
    "/api/v1/auth/me/",
  ]);
  for (const [, init] of fetchMock.mock.calls) {
    expect(init?.cache).toBe("no-store");
    expect(new Headers(init?.headers).has("X-CSRFToken")).toBe(false);
  }
  expect(local).not.toHaveBeenCalled();
});

test.each([
  {},
  null,
  [],
  { csrfToken: "" },
  { csrfToken: " " },
  { csrfToken: 1 },
  { csrf_token: csrfToken },
])("rejeita contrato CSRF inválido %j", async (payload) => {
  fetchMock.mockResolvedValue(jsonResponse(payload));
  await expect(getCsrfToken()).rejects.toMatchObject({
    failure: { kind: "invalid-response" },
  });
});

test.each([
  {},
  null,
  [],
  { ...user, id: "7" },
  { ...user, id: 1.5 },
  { ...user, id: 0 },
  { ...user, id: Number.MAX_SAFE_INTEGER + 1 },
  { ...user, email: "" },
  { ...user, email: 7 },
  { ...user, first_name: null },
  { ...user, last_name: undefined },
])("rejeita identidade inválida %j", async (payload) => {
  fetchMock.mockResolvedValue(jsonResponse(payload));
  await expect(getCurrentUser()).rejects.toMatchObject({
    failure: { kind: "invalid-response" },
  });
});

test("nomes vazios são permitidos e campos extras não viram identidade local", async () => {
  fetchMock.mockResolvedValue(
    jsonResponse({ ...user, first_name: "", last_name: "", extra: "ignored" }),
  );
  await expect(getCurrentUser()).resolves.toEqual({
    ...user,
    first_name: "",
    last_name: "",
  });
});

test("somente o 403 exato de /me vira ausência de sessão", async () => {
  fetchMock.mockResolvedValue(jsonResponse(anonymousPayload, 403));
  await expect(getCurrentUser()).resolves.toBeNull();
});

test.each([
  [403, { detail: "Você não tem permissão para executar essa ação." }],
  [403, { detail: anonymousPayload.detail + " Outra causa." }],
  [403, { detail: anonymousPayload.detail, extra: true }],
  [401, anonymousPayload],
  [500, anonymousPayload],
])(
  "HTTP %s não correspondente ao contrato anônimo continua como erro",
  async (status, payload) => {
    fetchMock.mockResolvedValue(jsonResponse(payload, status));
    await expect(getCurrentUser()).rejects.toMatchObject({
      failure: { kind: "http", status, data: payload },
    });
  },
);

test("403 na preparação CSRF nunca vira anonimato", async () => {
  fetchMock.mockResolvedValue(jsonResponse(anonymousPayload, 403));
  await expect(getCsrfToken()).rejects.toMatchObject({
    failure: { kind: "http", status: 403 },
  });
});

test("204 não satisfaz nenhum objeto obrigatório", async () => {
  fetchMock.mockImplementation(async () => new Response(null, { status: 204 }));
  await expect(getCsrfToken()).rejects.toMatchObject({
    failure: { kind: "invalid-response" },
  });
  await expect(getCurrentUser()).rejects.toMatchObject({
    failure: { kind: "invalid-response" },
  });
});
