import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { useAuthSession } from "./useAuthSession";
import * as authApi from "./api";
import {
  anonymousPayload,
  csrfToken,
  deferred,
  jsonResponse,
  user,
} from "../../test/apiFixtures";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

test.each(["resolve", "reject"] as const)(
  "resposta antiga (%s) não substitui tentativa mais recente mesmo sem respeitar abort",
  async (completion) => {
    const old = deferred<Response>();
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ csrfToken }))
      .mockReturnValueOnce(old.promise)
      .mockResolvedValueOnce(jsonResponse({ csrfToken }))
      .mockResolvedValueOnce(jsonResponse(user));
    const { result } = renderHook(() => useAuthSession());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const oldSignal = fetchMock.mock.calls[1][1]?.signal;
    act(() => result.current.verify());
    expect(oldSignal?.aborted).toBe(true);
    expect(result.current.state).toEqual({ status: "checking" });
    await waitFor(() =>
      expect(result.current.state).toEqual({ status: "authenticated", user }),
    );
    await act(async () => {
      if (completion === "resolve")
        old.resolve(jsonResponse(anonymousPayload, 403));
      else old.reject(new TypeError("late offline"));
    });
    expect(result.current.state).toEqual({ status: "authenticated", user });
    expect(fetchMock).toHaveBeenCalledTimes(4);
  },
);

test("nova verificação remove imediatamente a identidade anteriormente confirmada", async () => {
  const next = deferred<Response>();
  fetchMock
    .mockResolvedValueOnce(jsonResponse({ csrfToken }))
    .mockResolvedValueOnce(jsonResponse(user))
    .mockReturnValueOnce(next.promise)
    .mockResolvedValueOnce(jsonResponse(anonymousPayload, 403));
  const { result } = renderHook(() => useAuthSession());
  await waitFor(() =>
    expect(result.current.state.status).toBe("authenticated"),
  );
  act(() => result.current.verify());
  expect(result.current.state).toEqual({ status: "checking" });
  await act(async () => next.resolve(jsonResponse({ csrfToken })));
  await waitFor(() =>
    expect(result.current.state).toEqual({ status: "anonymous" }),
  );
});

test.each(["resolve", "reject"] as const)(
  "bootstrap antigo (%s) não desfaz login e logout posteriores mesmo se a API ignorar abort",
  async (completion) => {
    const old = deferred<authApi.UserIdentity | null>();
    vi.spyOn(authApi, "getCsrfToken").mockResolvedValue(csrfToken);
    const me = vi
      .spyOn(authApi, "getCurrentUser")
      .mockReturnValueOnce(old.promise)
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce(user)
      .mockResolvedValueOnce(null);
    const login = vi.spyOn(authApi, "login").mockResolvedValue(user);
    const logout = vi.spyOn(authApi, "logout").mockResolvedValue(undefined);
    const { result } = renderHook(() => useAuthSession());
    await waitFor(() => expect(me).toHaveBeenCalledTimes(1));
    const oldSignal = me.mock.calls[0][0];
    act(() => result.current.verify());
    await waitFor(() => expect(result.current.state.status).toBe("anonymous"));
    expect(oldSignal?.aborted).toBe(true);
    await act(async () =>
      result.current.login({
        email: "pessoa@example.test",
        password: "fictícia",
      }),
    );
    expect(result.current.state).toEqual({ status: "authenticated", user });
    await act(async () => result.current.logout());
    expect(result.current.state).toEqual({ status: "anonymous" });
    await act(async () => {
      if (completion === "resolve") old.resolve(user);
      else old.reject(new TypeError("late failure"));
    });
    expect(result.current.state).toEqual({ status: "anonymous" });
    expect(login).toHaveBeenCalledTimes(1);
    expect(logout).toHaveBeenCalledTimes(1);
  },
);

test("coordenador bloqueia login, logout e verificação conflitantes antes do React renderizar", async () => {
  const loginToken = deferred<string>();
  const logoutToken = deferred<string>();
  const csrf = vi
    .spyOn(authApi, "getCsrfToken")
    .mockResolvedValueOnce(csrfToken)
    .mockReturnValueOnce(loginToken.promise)
    .mockResolvedValueOnce(csrfToken)
    .mockReturnValueOnce(logoutToken.promise)
    .mockResolvedValueOnce(csrfToken);
  vi.spyOn(authApi, "getCurrentUser")
    .mockResolvedValueOnce(null)
    .mockResolvedValueOnce(user)
    .mockResolvedValueOnce(null);
  const login = vi.spyOn(authApi, "login").mockResolvedValue(user);
  const logout = vi.spyOn(authApi, "logout").mockResolvedValue(undefined);
  const { result } = renderHook(() => useAuthSession());
  await waitFor(() => expect(result.current.state.status).toBe("anonymous"));
  let entering: Promise<void>;
  act(() => {
    entering = result.current.login({
      email: "pessoa@example.test",
      password: "fictícia",
    });
    void result.current.login({
      email: "ignored@example.test",
      password: "ignored",
    });
    void result.current.logout();
    result.current.verify();
  });
  expect(csrf).toHaveBeenCalledTimes(2);
  expect(result.current.state.status).toBe("signing-in");
  await act(async () => {
    loginToken.resolve(csrfToken);
    await entering;
  });
  expect(login).toHaveBeenCalledTimes(1);
  expect(result.current.state.status).toBe("authenticated");
  let leaving: Promise<void>;
  act(() => {
    leaving = result.current.logout();
    void result.current.logout();
    void result.current.login({
      email: "ignored@example.test",
      password: "ignored",
    });
    result.current.verify();
  });
  expect(csrf).toHaveBeenCalledTimes(4);
  expect(result.current.state).toEqual({ status: "signing-out" });
  await act(async () => {
    logoutToken.resolve(csrfToken);
    await leaving;
  });
  expect(logout).toHaveBeenCalledTimes(1);
  expect(result.current.state).toEqual({ status: "anonymous" });
});

test.each(["login", "logout"] as const)(
  "cleanup invalida %s tardio mesmo quando a API ignora o sinal",
  async (operation) => {
    vi.spyOn(authApi, "getCsrfToken").mockResolvedValue(csrfToken);
    const me = vi
      .spyOn(authApi, "getCurrentUser")
      .mockResolvedValue(operation === "login" ? null : user);
    const pendingLogin = deferred<authApi.UserIdentity>();
    const pendingLogout = deferred<void>();
    const login = vi
      .spyOn(authApi, "login")
      .mockReturnValue(pendingLogin.promise);
    const logout = vi
      .spyOn(authApi, "logout")
      .mockReturnValue(pendingLogout.promise);
    const { result, unmount } = renderHook(() => useAuthSession());
    await waitFor(() =>
      expect(result.current.state.status).toBe(
        operation === "login" ? "anonymous" : "authenticated",
      ),
    );
    act(() => {
      if (operation === "login")
        void result.current.login({
          email: "pessoa@example.test",
          password: "fictícia",
        });
      else void result.current.logout();
    });
    await waitFor(() =>
      expect(operation === "login" ? login : logout).toHaveBeenCalledTimes(1),
    );
    const signal =
      operation === "login" ? login.mock.calls[0][2] : logout.mock.calls[0][1];
    unmount();
    expect(signal?.aborted).toBe(true);
    await act(async () => {
      if (operation === "login") pendingLogin.resolve(user);
      else pendingLogout.resolve(undefined);
    });
    expect(me).toHaveBeenCalledTimes(1);
  },
);
