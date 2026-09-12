import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { useSessionBootstrap } from "./useSessionBootstrap";
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
    const { result } = renderHook(() => useSessionBootstrap());
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const oldSignal = fetchMock.mock.calls[1][1]?.signal;
    act(() => result.current.retry());
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
  const { result } = renderHook(() => useSessionBootstrap());
  await waitFor(() =>
    expect(result.current.state.status).toBe("authenticated"),
  );
  act(() => result.current.retry());
  expect(result.current.state).toEqual({ status: "checking" });
  await act(async () => next.resolve(jsonResponse({ csrfToken })));
  await waitFor(() =>
    expect(result.current.state).toEqual({ status: "anonymous" }),
  );
});
