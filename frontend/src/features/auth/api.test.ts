import { beforeEach, expect, test, vi } from "vitest";
import {
  getCsrfToken,
  getCurrentUser,
  login,
  logout,
  getLoginRejection,
} from "./api";
import { ApiError } from "../../shared/api/client";
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

test("login exige 200 e identidade válida, enviando a senha sem transformação", async () => {
  fetchMock.mockResolvedValue(jsonResponse(user));
  const credentials = {
    email: "Pessoa@EXAMPLE.test",
    password: "  senha fictícia  ",
  };
  await expect(login(credentials, csrfToken)).resolves.toEqual(user);
  const [path, init] = fetchMock.mock.calls[0];
  expect(path).toBe("/api/v1/auth/login/");
  expect(init).toMatchObject({
    method: "POST",
    credentials: "same-origin",
    mode: "same-origin",
    redirect: "error",
    cache: "no-store",
  });
  expect(init?.body).toBe(JSON.stringify(credentials));
  expect(new Headers(init?.headers).get("X-CSRFToken")).toBe(csrfToken);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test.each([{}, null, [], { ...user, id: "7" }, { ...user, email: "" }])(
  "login rejeita identidade inválida %j",
  async (payload) => {
    fetchMock.mockResolvedValue(jsonResponse(payload));
    await expect(
      login({ email: "pessoa@example.test", password: "fictícia" }, csrfToken),
    ).rejects.toMatchObject({ failure: { kind: "invalid-response" } });
  },
);

test.each([201, 202, 204])(
  "login não aceita status %s inesperado",
  async (status) => {
    fetchMock.mockResolvedValue(
      status === 204
        ? new Response(null, { status })
        : jsonResponse(user, status),
    );
    await expect(
      login({ email: "pessoa@example.test", password: "fictícia" }, csrfToken),
    ).rejects.toMatchObject({ failure: { kind: "invalid-response" } });
  },
);

test("logout aceita somente 204 e não lê corpo nem envia JSON inventado", async () => {
  const response = new Response(null, { status: 204 });
  const read = vi.spyOn(response, "text");
  fetchMock.mockResolvedValue(response);
  await expect(logout(csrfToken)).resolves.toBeUndefined();
  const [path, init] = fetchMock.mock.calls[0];
  expect(path).toBe("/api/v1/auth/logout/");
  expect(init).toMatchObject({
    method: "POST",
    credentials: "same-origin",
    mode: "same-origin",
  });
  expect(init?.body).toBeUndefined();
  expect(new Headers(init?.headers).get("X-CSRFToken")).toBe(csrfToken);
  expect(read).not.toHaveBeenCalled();
});

test.each([200, 201, 202])(
  "logout não aceita status %s com JSON",
  async (status) => {
    fetchMock.mockResolvedValue(jsonResponse({}, status));
    await expect(logout(csrfToken)).rejects.toMatchObject({
      failure: { kind: "invalid-response" },
    });
  },
);

test("logout mantém o 403 como falha, sem convertê-lo em sucesso ou anonimato", async () => {
  fetchMock.mockResolvedValue(jsonResponse(anonymousPayload, 403));
  await expect(logout(csrfToken)).rejects.toMatchObject({
    failure: { kind: "http", status: 403 },
  });
});

test("distingue credenciais, campos e rejeição CSRF sem mostrar mensagens brutas", () => {
  const failure = (status: number, data: unknown) =>
    new ApiError({ kind: "http", status, data });
  expect(
    getLoginRejection(failure(400, { detail: "Credenciais inválidas." })),
  ).toEqual({ message: "E-mail ou senha inválidos" });
  expect(
    getLoginRejection(
      failure(400, {
        email: ["private traceback"],
        password: ["sensitive data"],
      }),
    ),
  ).toEqual({
    message: "Confira os campos indicados.",
    fields: {
      email: "Confira o e-mail informado.",
      password: "Confira a senha informada.",
    },
  });
  expect(getLoginRejection(failure(403, undefined))?.message).toContain("CSRF");
  for (const error of [
    failure(400, { detail: "Credenciais inválidas.", extra: true }),
    failure(400, { email: [] }),
    failure(400, { email: [null] }),
    failure(400, { unknown: ["error"] }),
    failure(500, { detail: "Credenciais inválidas." }),
    new ApiError({ kind: "network" }),
  ])
    expect(getLoginRejection(error)).toBeUndefined();
});

test.each([getCsrfToken, getCurrentUser])(
  "leituras também rejeitam 201 com payload plausível",
  async (operation) => {
    fetchMock.mockResolvedValue(jsonResponse({ ...user, csrfToken }, 201));
    await expect(operation()).rejects.toMatchObject({
      failure: { kind: "invalid-response" },
    });
  },
);
