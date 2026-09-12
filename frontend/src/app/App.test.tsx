import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import App from "./App";
import {
  anonymousPayload,
  csrfToken,
  deferred,
  jsonResponse,
  user,
} from "../test/apiFixtures";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

test("preserva main e heading e consulta CSRF antes de apresentar ausência de sessão", async () => {
  const csrf = deferred<Response>();
  fetchMock
    .mockReturnValueOnce(csrf.promise)
    .mockResolvedValueOnce(jsonResponse(anonymousPayload, 403));
  render(<App />);
  const main = screen.getByRole("main");
  expect(
    within(main).getByRole("heading", { name: "ObraControl", level: 1 }),
  ).toBeVisible();
  expect(within(main).getByText("Etapa F2 · Integração inicial")).toBeVisible();
  expect(screen.getByRole("status")).toHaveTextContent("Verificando sessão…");
  expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
    "/api/v1/auth/csrf/",
  ]);
  await act(async () => csrf.resolve(jsonResponse({ csrfToken })));
  expect(await screen.findByText("Nenhuma sessão autenticada")).toBeVisible();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
    "/api/v1/auth/csrf/",
    "/api/v1/auth/me/",
  ]);
});

test("apresenta a identidade recebida sem inferir roles ou carregar módulos empresariais", async () => {
  fetchMock
    .mockResolvedValueOnce(jsonResponse({ csrfToken }))
    .mockResolvedValueOnce(jsonResponse(user));
  render(<App />);
  expect(await screen.findByText(user.email)).toBeVisible();
  expect(screen.getByRole("status")).toHaveTextContent("Sessão autenticada:");
  expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
    "/api/v1/auth/csrf/",
    "/api/v1/auth/me/",
  ]);
});

test.each([
  ["CSRF HTTP", "csrf"],
  ["CSRF inválido", "csrf-invalid"],
  ["rede", "network"],
  ["me HTTP", "me-http"],
  ["me HTML", "me-html"],
  ["me inválido", "me-invalid"],
] as const)(
  "falha de %s apresenta mensagem segura e retry, sem fingir anonimato",
  async (_, failure) => {
    if (failure === "network")
      fetchMock.mockRejectedValueOnce(new TypeError("private traceback"));
    else if (failure === "csrf")
      fetchMock.mockResolvedValueOnce(jsonResponse(anonymousPayload, 403));
    else if (failure === "csrf-invalid")
      fetchMock.mockResolvedValueOnce(jsonResponse({}));
    else {
      fetchMock.mockResolvedValueOnce(jsonResponse({ csrfToken }));
      if (failure === "me-http")
        fetchMock.mockResolvedValueOnce(
          jsonResponse({ detail: "private traceback" }, 500),
        );
      if (failure === "me-html")
        fetchMock.mockResolvedValueOnce(
          new Response("<html>private traceback</html>", {
            headers: { "Content-Type": "text/html" },
          }),
        );
      if (failure === "me-invalid")
        fetchMock.mockResolvedValueOnce(jsonResponse({}));
    }
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível verificar a sessão. Tente novamente.",
    );
    expect(
      screen.getByRole("button", { name: "Tentar novamente" }),
    ).toBeVisible();
    expect(
      screen.queryByText("Nenhuma sessão autenticada"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/private|traceback/)).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(failure.startsWith("me-") ? 2 : 1);
  },
);

test("timeout mantém estado de erro, sem retry automático", async () => {
  vi.useFakeTimers();
  fetchMock.mockReturnValue(deferred<Response>().promise);
  render(<App />);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(15_000);
  });
  expect(screen.getByRole("alert")).toBeVisible();
  expect(
    screen.queryByText("Nenhuma sessão autenticada"),
  ).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("retry explícito retorna a checking e pode confirmar a identidade", async () => {
  const retryCsrf = deferred<Response>();
  fetchMock
    .mockRejectedValueOnce(new TypeError("offline"))
    .mockReturnValueOnce(retryCsrf.promise)
    .mockResolvedValueOnce(jsonResponse(user));
  render(<App />);
  const retry = await screen.findByRole("button", { name: "Tentar novamente" });
  retry.focus();
  expect(retry).toHaveFocus();
  fireEvent.click(retry);
  expect(screen.getByRole("status")).toHaveTextContent("Verificando sessão…");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await act(async () => retryCsrf.resolve(jsonResponse({ csrfToken })));
  expect(await screen.findByText(user.email)).toBeVisible();
  expect(fetchMock).toHaveBeenCalledTimes(3);
});

test("StrictMode cancela o primeiro efeito e inicializa novamente com controller válido", async () => {
  const signalsAtStart: boolean[] = [];
  fetchMock.mockImplementation(async (path, init) => {
    signalsAtStart.push(init?.signal?.aborted ?? false);
    return path === "/api/v1/auth/csrf/"
      ? jsonResponse({ csrfToken })
      : jsonResponse(anonymousPayload, 403);
  });
  render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
  expect(await screen.findByText("Nenhuma sessão autenticada")).toBeVisible();
  expect(signalsAtStart.every((aborted) => !aborted)).toBe(true);
  expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
    "/api/v1/auth/csrf/",
    "/api/v1/auth/csrf/",
    "/api/v1/auth/me/",
  ]);
});

test("cleanup cancela consulta e resposta tardia após unmount não inicia /me", async () => {
  const csrf = deferred<Response>();
  fetchMock.mockReturnValue(csrf.promise);
  const { unmount } = render(<App />);
  const signal = fetchMock.mock.calls[0][1]?.signal;
  unmount();
  expect(signal?.aborted).toBe(true);
  await act(async () => csrf.resolve(jsonResponse({ csrfToken })));
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("main")).not.toBeInTheDocument();
});
