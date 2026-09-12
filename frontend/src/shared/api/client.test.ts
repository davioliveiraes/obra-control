import { beforeEach, expect, test, vi } from "vitest";
import { ApiError, request } from "./client";
import { csrfToken, deferred, jsonResponse } from "../../test/apiFixtures";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

test("normaliza o caminho e fixa origem, cookies, Accept e redirects sem aceitar overrides", async () => {
  fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
  const options = {
    method: "GET" as const,
    csrfToken,
    credentials: "omit",
    mode: "cors",
    redirect: "follow",
    headers: { Authorization: "Bearer ignored" },
  };
  await expect(
    request("/api/v1/unused/../auth/me/?check=1", options),
  ).resolves.toEqual({ ok: true });
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [path, init] = fetchMock.mock.calls[0];
  expect(path).toBe("/api/v1/auth/me/?check=1");
  expect(init).toMatchObject({
    method: "GET",
    credentials: "same-origin",
    mode: "same-origin",
    redirect: "error",
  });
  const headers = new Headers(init?.headers);
  expect(headers.get("Accept")).toBe("application/json");
  expect(headers.has("X-CSRFToken")).toBe(false);
  expect(headers.has("Authorization")).toBe(false);
  expect(headers.has("Content-Type")).toBe(false);
  expect(init?.body).toBeUndefined();
});

test("204 não tenta ler nem interpretar o corpo", async () => {
  const response = new Response(null, { status: 204 });
  const read = vi.spyOn(response, "text");
  fetchMock.mockResolvedValue(response);
  await expect(request("/api/v1/empty/")).resolves.toBeUndefined();
  expect(read).not.toHaveBeenCalled();
});

test.each(["POST", "PUT", "PATCH", "DELETE"] as const)(
  "%s envia JSON e CSRF explícito",
  async (method) => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    await request("/api/v1/resource/", {
      method,
      csrfToken,
      json: { name: "Teste" },
    });
    const init = fetchMock.mock.calls[0][1];
    expect(init?.method).toBe(method);
    expect(init?.body).toBe('{"name":"Teste"}');
    const headers = new Headers(init?.headers);
    expect(headers.get("X-CSRFToken")).toBe(csrfToken);
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  },
);

test.each(["POST", "PUT", "PATCH", "DELETE"] as const)(
  "%s sem CSRF é rejeitado antes da rede",
  async (method) => {
    await expect(
      request("/api/v1/resource/", { method, json: {} }),
    ).rejects.toMatchObject({ failure: { kind: "invalid-request" } });
    expect(fetchMock).not.toHaveBeenCalled();
  },
);

test.each(["", " ", "invalid\r\nheader"])(
  "rejeita token ausente ou impróprio para header",
  async (token) => {
    await expect(
      request("/api/v1/resource/", { method: "POST", csrfToken: token }),
    ).rejects.toMatchObject({ failure: { kind: "invalid-request" } });
    expect(fetchMock).not.toHaveBeenCalled();
  },
);

test("rejeita corpo em GET e JSON não serializável", async () => {
  await expect(
    request("/api/v1/resource/", { json: {} }),
  ).rejects.toMatchObject({ failure: { kind: "invalid-request" } });
  await expect(
    request("/api/v1/resource/", { method: "POST", csrfToken, json: 1n }),
  ).rejects.toMatchObject({ failure: { kind: "invalid-request" } });
  expect(fetchMock).not.toHaveBeenCalled();
});

test.each([
  "https://example.test/api/v1/auth/me/",
  "//example.test/api/v1/auth/me/",
  "api/v1/auth/me/",
  "/api/v10/auth/me/",
  "/api/v1",
  "/api/v1/../../admin/",
  "/api/v1/%2e%2e/%2e%2e/admin/",
  "/api/v1/%2f..%2f..%2fadmin/",
  "/api/v1/%252e%252e/admin/",
  "/api/v1/%5cadmin/",
  "/api/v1/\\admin/",
  "/api/v1/auth/me/#fragment",
  "/api/v1/invalid%",
  "/api/v1/%00",
  "/api/v1/\u0000",
])("rejeita URL externa ou escape da base: %s", async (path) => {
  await expect(request(path)).rejects.toMatchObject({
    failure: { kind: "invalid-request" },
  });
  expect(fetchMock).not.toHaveBeenCalled();
});

test.each([403, 500])(
  "preserva status %s e JSON estruturado sem efeitos de sessão ou retry",
  async (status) => {
    const data = {
      detail: "Erro representativo.",
      fields: { email: ["Inválido."] },
    };
    fetchMock.mockResolvedValue(jsonResponse(data, status));
    await expect(request("/api/v1/resource/")).rejects.toMatchObject({
      failure: { kind: "http", status, data },
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/resource/");
  },
);

test.each([
  [403, "text/html", "<html>private traceback</html>"],
  [500, "text/plain", "private traceback"],
  [403, "application/json", "{invalid"],
  [500, "application/json", ""],
])(
  "mantém status %s com corpo inválido e não expõe texto",
  async (status, contentType, body) => {
    fetchMock.mockResolvedValue(
      new Response(body, { status, headers: { "Content-Type": contentType } }),
    );
    const error = await request("/api/v1/resource/").catch(
      (failure: unknown) => failure,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      failure: { kind: "http", status, data: undefined },
    });
    expect(String(error)).not.toMatch(/private|traceback|html|invalid/);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  },
);

test("uma falha de leitura não apaga o status HTTP já recebido", async () => {
  const response = jsonResponse({}, 500);
  vi.spyOn(response, "text").mockRejectedValue(
    new TypeError("connection lost"),
  );
  fetchMock.mockResolvedValue(response);
  await expect(request("/api/v1/resource/")).rejects.toMatchObject({
    failure: { kind: "http", status: 500, data: undefined },
  });
});

test.each([
  ["text/html", "<html>SPA fallback</html>"],
  ["text/plain", "ok"],
  ["application/json", "{invalid"],
  ["application/json", ""],
])("rejeita sucesso inválido %s", async (contentType, body) => {
  fetchMock.mockResolvedValue(
    new Response(body, { headers: { "Content-Type": contentType } }),
  );
  await expect(request("/api/v1/resource/")).rejects.toMatchObject({
    failure: { kind: "invalid-response" },
  });
});

test("falha de rede é distinta de HTTP e não faz retry", async () => {
  fetchMock.mockRejectedValue(new TypeError("Sensitive network detail"));
  const error = await request("/api/v1/resource/").catch(
    (failure: unknown) => failure,
  );
  expect(error).toMatchObject({ failure: { kind: "network" } });
  expect(String(error)).not.toContain("Sensitive");
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("rejeita resposta já redirecionada defensivamente", async () => {
  const response = jsonResponse({});
  Object.defineProperty(response, "redirected", { value: true });
  fetchMock.mockResolvedValue(response);
  await expect(request("/api/v1/resource/")).rejects.toMatchObject({
    failure: { kind: "invalid-response" },
  });
});

test.each(["headers", "body"] as const)(
  "timeout de 15 segundos cobre %s mesmo se o mock ignorar abort",
  async (phase) => {
    vi.useFakeTimers();
    if (phase === "headers") {
      fetchMock.mockReturnValue(deferred<Response>().promise);
    } else {
      const response = jsonResponse({});
      vi.spyOn(response, "text").mockReturnValue(deferred<string>().promise);
      fetchMock.mockResolvedValue(response);
    }
    const pending = request("/api/v1/resource/");
    const rejected = expect(pending).rejects.toMatchObject({
      failure: { kind: "timeout" },
    });
    await vi.advanceTimersByTimeAsync(14_999);
    expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await rejected;
    expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  },
);

test.each(["headers", "body"] as const)(
  "cancelamento do chamador durante %s não vira erro de rede",
  async (phase) => {
    const caller = new AbortController();
    if (phase === "headers") {
      fetchMock.mockReturnValue(deferred<Response>().promise);
    } else {
      const response = jsonResponse({});
      vi.spyOn(response, "text").mockReturnValue(deferred<string>().promise);
      fetchMock.mockResolvedValue(response);
    }
    const removed = vi.spyOn(caller.signal, "removeEventListener");
    const pending = request("/api/v1/resource/", { signal: caller.signal });
    const rejected = expect(pending).rejects.toMatchObject({
      failure: { kind: "aborted" },
    });
    await Promise.resolve();
    caller.abort("do not expose this reason");
    await rejected;
    expect(fetchMock.mock.calls[0][1]?.signal?.aborted).toBe(true);
    expect(removed).toHaveBeenCalledWith("abort", expect.any(Function));
  },
);

test("sinal previamente abortado não faz requisição", async () => {
  const caller = new AbortController();
  caller.abort();
  await expect(
    request("/api/v1/resource/", { signal: caller.signal }),
  ).rejects.toMatchObject({ failure: { kind: "aborted" } });
  expect(fetchMock).not.toHaveBeenCalled();
});

test("limpa timer e listener também depois do sucesso", async () => {
  vi.useFakeTimers();
  const caller = new AbortController();
  const removed = vi.spyOn(caller.signal, "removeEventListener");
  fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
  await request("/api/v1/resource/", { signal: caller.signal });
  expect(removed).toHaveBeenCalledWith("abort", expect.any(Function));
  expect(vi.getTimerCount()).toBe(0);
  expect(caller.signal.aborted).toBe(false);
});
