import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import App from "./App";
import * as organizationsApi from "../features/organizations/api";
import {
  anonymousPayload,
  csrfToken,
  deferred,
  jsonResponse,
  user,
} from "../test/apiFixtures";

const fetchMock = vi.fn<typeof fetch>();
const rotatedToken = "b".repeat(64);
const credentials = {
  email: "entrada@example.test",
  password: "  senha fictícia  ",
};

beforeEach(() => {
  vi.spyOn(organizationsApi, "listOrganizations").mockResolvedValue([]);
  vi.spyOn(organizationsApi, "getCurrentOrganization").mockResolvedValue(null);
  vi.stubGlobal("BroadcastChannel", undefined);
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

async function anonymousApp() {
  fetchMock
    .mockResolvedValueOnce(jsonResponse({ csrfToken }))
    .mockResolvedValueOnce(jsonResponse(anonymousPayload, 403));
  const view = render(<App />);
  await screen.findByRole("form", { name: "Entrar na conta" });
  return view;
}

async function authenticatedApp() {
  fetchMock
    .mockResolvedValueOnce(jsonResponse({ csrfToken }))
    .mockResolvedValueOnce(jsonResponse(user));
  const view = render(<App />);
  await screen.findByRole("button", { name: "Sair" });
  return view;
}

function fillForm() {
  fireEvent.change(screen.getByRole("textbox", { name: "E-mail" }), {
    target: { value: credentials.email },
  });
  fireEvent.change(screen.getByLabelText("Senha"), {
    target: { value: credentials.password },
  });
}

function submit() {
  fireEvent.submit(screen.getByRole("form", { name: "Entrar na conta" }));
}

function posts() {
  return fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
}

test("formulário tem labels, tipos, autocomplete e validação obrigatória sem política de cadastro", async () => {
  await anonymousApp();
  const email = screen.getByRole("textbox", { name: "E-mail" });
  const password = screen.getByLabelText("Senha");
  expect(email).toHaveAttribute("type", "email");
  expect(email).toHaveAttribute("name", "email");
  expect(email).toHaveAttribute("autocomplete", "username");
  expect(email).toBeRequired();
  expect(password).toHaveAttribute("type", "password");
  expect(password).toHaveAttribute("name", "password");
  expect(password).toHaveAttribute("autocomplete", "current-password");
  expect(password).toBeRequired();
  expect(password).not.toHaveAttribute("minlength");
  expect(password).not.toHaveAttribute("pattern");
  expect(screen.getByRole("button", { name: "Entrar" })).toHaveAttribute(
    "type",
    "submit",
  );
  submit();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  fireEvent.change(email, { target: { value: "invalid" } });
  fireEvent.change(password, { target: { value: credentials.password } });
  submit();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  fireEvent.change(email, { target: { value: credentials.email } });
  fireEvent.change(password, { target: { value: "" } });
  submit();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("login usa novo CSRF, aguarda /me e não publica o email digitado ou a identidade do POST", async () => {
  await anonymousApp();
  const confirmed = deferred<Response>();
  fetchMock
    .mockResolvedValueOnce(jsonResponse({ csrfToken }))
    .mockResolvedValueOnce(
      jsonResponse({ ...user, email: "post@example.test" }),
    )
    .mockResolvedValueOnce(jsonResponse({ csrfToken: rotatedToken }))
    .mockReturnValueOnce(confirmed.promise);
  fillForm();
  const password = screen.getByLabelText("Senha");
  submit();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(6));
  expect(screen.getByRole("status")).toHaveTextContent("Verificando sessão…");
  expect(screen.queryByText("post@example.test")).not.toBeInTheDocument();
  expect(screen.queryByText(credentials.email)).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Sair" }),
  ).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
    "/api/v1/auth/csrf/",
    "/api/v1/auth/me/",
    "/api/v1/auth/csrf/",
    "/api/v1/auth/login/",
    "/api/v1/auth/csrf/",
    "/api/v1/auth/me/",
  ]);
  const post = posts()[0][1];
  expect(post?.body).toBe(JSON.stringify(credentials));
  expect(post?.credentials).toBe("same-origin");
  expect(new Headers(post?.headers).get("X-CSRFToken")).toBe(csrfToken);
  await act(async () => confirmed.resolve(jsonResponse(user)));
  expect(await screen.findByText(user.email)).toBeVisible();
  expect(password).toHaveValue("");
  expect(
    screen.getByText("Os módulos ainda não estão disponíveis."),
  ).toBeVisible();
  expect(posts()).toHaveLength(1);
});

test("bloqueia duplicidade também antes de uma nova renderização e limpa senha ao rejeitar", async () => {
  await anonymousApp();
  const preparation = deferred<Response>();
  fetchMock
    .mockReturnValueOnce(preparation.promise)
    .mockResolvedValueOnce(
      jsonResponse({ detail: "Credenciais inválidas." }, 400),
    );
  fillForm();
  const form = screen.getByRole("form", { name: "Entrar na conta" });
  act(() => {
    fireEvent.submit(form);
    fireEvent.submit(form);
  });
  expect(screen.getByRole("button", { name: "Entrando…" })).toBeDisabled();
  expect(screen.getByRole("textbox", { name: "E-mail" })).toBeDisabled();
  expect(screen.getByLabelText("Senha")).toBeDisabled();
  expect(fetchMock).toHaveBeenCalledTimes(3);
  await act(async () => preparation.resolve(jsonResponse({ csrfToken })));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "E-mail ou senha inválidos",
  );
  expect(screen.getByRole("textbox", { name: "E-mail" })).toHaveValue(
    credentials.email,
  );
  expect(screen.getByLabelText("Senha")).toHaveValue("");
  expect(posts()).toHaveLength(1);
});

test("associa erros de campo sem expor texto arbitrário recebido do backend", async () => {
  await anonymousApp();
  fetchMock
    .mockResolvedValueOnce(jsonResponse({ csrfToken }))
    .mockResolvedValueOnce(
      jsonResponse(
        { email: ["private traceback"], password: ["private data"] },
        400,
      ),
    );
  fillForm();
  submit();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Confira os campos indicados.",
  );
  expect(screen.getByRole("textbox", { name: "E-mail" })).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  expect(
    screen.getByRole("textbox", { name: "E-mail" }),
  ).toHaveAccessibleDescription("Confira o e-mail informado.");
  expect(screen.getByLabelText("Senha")).toHaveAccessibleDescription(
    "Confira a senha informada.",
  );
  expect(screen.getByLabelText("Senha")).toHaveValue("");
  expect(screen.queryByText(/private|traceback/)).not.toBeInTheDocument();
  expect(posts()).toHaveLength(1);
});

test("rejeição CSRF do login não faz retry automático nem expõe HTML", async () => {
  await anonymousApp();
  fetchMock
    .mockResolvedValueOnce(jsonResponse({ csrfToken }))
    .mockResolvedValueOnce(
      new Response("<html>private traceback CSRF</html>", {
        status: 403,
        headers: { "Content-Type": "text/html" },
      }),
    );
  fillForm();
  submit();
  expect(await screen.findByRole("alert")).toHaveTextContent("proteção CSRF");
  expect(screen.getByLabelText("Senha")).toHaveValue("");
  expect(screen.queryByText(/private|traceback/)).not.toBeInTheDocument();
  expect(posts()).toHaveLength(1);
  expect(fetchMock).toHaveBeenCalledTimes(4);
});

test.each(["network", "payload"] as const)(
  "falha preparatória %s impede o POST e limpa a senha",
  async (failure) => {
    await anonymousApp();
    if (failure === "network")
      fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    else fetchMock.mockResolvedValueOnce(jsonResponse({}));
    fillForm();
    const password = screen.getByLabelText("Senha");
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Nenhum login foi enviado.",
    );
    expect(password).toHaveValue("");
    expect(posts()).toHaveLength(0);
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Verificar sessão" }),
    ).toBeVisible();
  },
);

test.each(["network", "html", "json", "204", "201", "500", "400"] as const)(
  "resultado de login não confirmado (%s) recupera somente por GET",
  async (failure) => {
    await anonymousApp();
    fetchMock.mockResolvedValueOnce(jsonResponse({ csrfToken }));
    if (failure === "network")
      fetchMock.mockRejectedValueOnce(new TypeError("response lost"));
    if (failure === "html")
      fetchMock.mockResolvedValueOnce(
        new Response("<html>private</html>", {
          headers: { "Content-Type": "text/html" },
        }),
      );
    if (failure === "json") fetchMock.mockResolvedValueOnce(jsonResponse({}));
    if (failure === "204")
      fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    if (failure === "201")
      fetchMock.mockResolvedValueOnce(jsonResponse(user, 201));
    if (failure === "500")
      fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "private" }, 500));
    if (failure === "400")
      fetchMock.mockResolvedValueOnce(
        jsonResponse({ unexpected: "private" }, 400),
      );
    fillForm();
    const password = screen.getByLabelText("Senha");
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível confirmar a entrada.",
    );
    expect(password).toHaveValue("");
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    expect(screen.queryByText(user.email)).not.toBeInTheDocument();
    expect(posts()).toHaveLength(1);
    const before = fetchMock.mock.calls.length;
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ csrfToken: rotatedToken }))
      .mockResolvedValueOnce(jsonResponse(user));
    fireEvent.click(screen.getByRole("button", { name: "Verificar sessão" }));
    expect(await screen.findByText(user.email)).toBeVisible();
    expect(
      fetchMock.mock.calls
        .slice(before)
        .map(([path, init]) => [path, init?.method]),
    ).toEqual([
      ["/api/v1/auth/csrf/", "GET"],
      ["/api/v1/auth/me/", "GET"],
    ]);
    expect(posts()).toHaveLength(1);
  },
);

test("timeout do POST não presume rollback e oferece leitura sem repetir credenciais", async () => {
  await anonymousApp();
  vi.useFakeTimers();
  fetchMock
    .mockResolvedValueOnce(jsonResponse({ csrfToken }))
    .mockReturnValueOnce(deferred<Response>().promise);
  fillForm();
  await act(async () => {
    submit();
    await vi.advanceTimersByTimeAsync(15_000);
  });
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Não foi possível confirmar a entrada.",
  );
  expect(
    screen.getByRole("button", { name: "Verificar sessão" }),
  ).toBeVisible();
  expect(posts()).toHaveLength(1);
  expect(fetchMock).toHaveBeenCalledTimes(4);
});

test.each(["csrf", "me"] as const)(
  "login 200 seguido de falha em %s não acusa senha inválida",
  async (phase) => {
    await anonymousApp();
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ csrfToken }))
      .mockResolvedValueOnce(jsonResponse(user));
    if (phase === "me")
      fetchMock.mockResolvedValueOnce(
        jsonResponse({ csrfToken: rotatedToken }),
      );
    fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    fillForm();
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Não foi possível confirmar a entrada.",
    );
    expect(
      screen.queryByText("E-mail ou senha inválidos"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(user.email)).not.toBeInTheDocument();
    expect(posts()).toHaveLength(1);
  },
);

test("logout usa CSRF atual, remove a identidade e aguarda confirmação anônima", async () => {
  await authenticatedApp();
  const response = deferred<Response>();
  const me = deferred<Response>();
  fetchMock
    .mockResolvedValueOnce(jsonResponse({ csrfToken: rotatedToken }))
    .mockReturnValueOnce(response.promise)
    .mockResolvedValueOnce(jsonResponse({ csrfToken }))
    .mockReturnValueOnce(me.promise);
  fireEvent.click(screen.getByRole("button", { name: "Sair" }));
  expect(screen.getByRole("status")).toHaveTextContent("Saindo…");
  expect(screen.queryByText(user.email)).not.toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  await waitFor(() => expect(posts()).toHaveLength(1));
  expect(posts()[0][0]).toBe("/api/v1/auth/logout/");
  expect(posts()[0][1]?.body).toBeUndefined();
  expect(new Headers(posts()[0][1]?.headers).get("X-CSRFToken")).toBe(
    rotatedToken,
  );
  await act(async () => response.resolve(new Response(null, { status: 204 })));
  expect(screen.getByRole("status")).toHaveTextContent("Verificando sessão…");
  expect(screen.queryByRole("form")).not.toBeInTheDocument();
  await act(async () => me.resolve(jsonResponse(anonymousPayload, 403)));
  expect(await screen.findByRole("form")).toBeVisible();
  expect(screen.getByRole("status")).toHaveTextContent(
    "Nenhuma sessão autenticada",
  );
  expect(posts()).toHaveLength(1);
});

test("leitura atual autenticada após logout não força anonimato", async () => {
  await authenticatedApp();
  const currentUser = { ...user, id: 8, email: "atual@example.test" };
  fetchMock
    .mockResolvedValueOnce(jsonResponse({ csrfToken }))
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(jsonResponse({ csrfToken: rotatedToken }))
    .mockResolvedValueOnce(jsonResponse(currentUser));
  fireEvent.click(screen.getByRole("button", { name: "Sair" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "A saída não foi confirmada.",
  );
  expect(screen.getByText(currentUser.email)).toBeVisible();
  expect(screen.queryByText(user.email)).not.toBeInTheDocument();
  expect(screen.queryByRole("form")).not.toBeInTheDocument();
});

test.each(["preparation", "403", "network", "200", "confirmation"] as const)(
  "falha de logout (%s) não restaura usuário e recuperação não repete POST",
  async (failure) => {
    await authenticatedApp();
    if (failure === "preparation")
      fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    else {
      fetchMock.mockResolvedValueOnce(jsonResponse({ csrfToken }));
      if (failure === "403")
        fetchMock.mockResolvedValueOnce(
          jsonResponse({ detail: "CSRF Failed: private" }, 403),
        );
      if (failure === "network")
        fetchMock.mockRejectedValueOnce(new TypeError("response lost"));
      if (failure === "200") fetchMock.mockResolvedValueOnce(jsonResponse({}));
      if (failure === "confirmation") {
        fetchMock
          .mockResolvedValueOnce(new Response(null, { status: 204 }))
          .mockResolvedValueOnce(jsonResponse({ csrfToken: rotatedToken }))
          .mockRejectedValueOnce(new TypeError("offline"));
      }
    }
    fireEvent.click(screen.getByRole("button", { name: "Sair" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      failure === "preparation"
        ? "Nenhum logout foi enviado."
        : failure === "403"
          ? "A saída foi recusada."
          : "Não foi possível confirmar a saída.",
    );
    expect(screen.queryByText(user.email)).not.toBeInTheDocument();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    const count = posts().length;
    const before = fetchMock.mock.calls.length;
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ csrfToken }))
      .mockResolvedValueOnce(jsonResponse(anonymousPayload, 403));
    fireEvent.click(screen.getByRole("button", { name: "Verificar sessão" }));
    expect(await screen.findByRole("form")).toBeVisible();
    expect(posts()).toHaveLength(count);
    expect(count).toBe(failure === "preparation" ? 0 : 1);
    expect(
      fetchMock.mock.calls
        .slice(before)
        .every(([, init]) => init?.method === "GET"),
    ).toBe(true);
  },
);

test("cleanup durante login cancela espera e não inicia confirmação depois de desmontar", async () => {
  const { unmount } = await anonymousApp();
  const response = deferred<Response>();
  fetchMock
    .mockResolvedValueOnce(jsonResponse({ csrfToken }))
    .mockReturnValueOnce(response.promise);
  fillForm();
  submit();
  await waitFor(() => expect(posts()).toHaveLength(1));
  const signal = posts()[0][1]?.signal;
  unmount();
  expect(signal?.aborted).toBe(true);
  await act(async () => response.resolve(jsonResponse(user)));
  expect(fetchMock).toHaveBeenCalledTimes(4);
});

test("StrictMode não dispara mutações; uma ação de login envia um único POST", async () => {
  let authenticated = false;
  fetchMock.mockImplementation(async (path) => {
    if (path === "/api/v1/auth/csrf/") return jsonResponse({ csrfToken });
    if (path === "/api/v1/auth/login/") {
      authenticated = true;
      return jsonResponse(user);
    }
    return authenticated
      ? jsonResponse(user)
      : jsonResponse(anonymousPayload, 403);
  });
  const { unmount } = render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
  await screen.findByRole("form");
  expect(posts()).toHaveLength(0);
  fillForm();
  submit();
  expect(await screen.findByText(user.email)).toBeVisible();
  expect(posts()).toHaveLength(1);
  unmount();
  render(<App />);
  expect(await screen.findByText(user.email)).toBeVisible();
  expect(posts()).toHaveLength(1);
});
