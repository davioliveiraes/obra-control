import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import App from "./App";
import * as auth from "../features/auth/api";
import * as api from "../features/organizations/api";
import { ApiError } from "../shared/api/client";
import { csrfToken, deferred, user } from "../test/apiFixtures";
import {
  firstOrganization as first,
  secondOrganization as second,
  TestChannel,
} from "../test/organizationFixtures";

let identity: auth.UserIdentity | null;
let organizations: api.AccessibleOrganization[];
let selected: api.AccessibleOrganization | null;

beforeEach(() => {
  identity = user;
  organizations = [first, second];
  selected = null;
  TestChannel.instances = [];
  vi.stubGlobal("BroadcastChannel", TestChannel);
  vi.spyOn(auth, "getCsrfToken").mockResolvedValue(csrfToken);
  vi.spyOn(auth, "getCurrentUser").mockImplementation(async () => identity);
  vi.spyOn(auth, "login").mockImplementation(async () => {
    identity = user;
    return user;
  });
  vi.spyOn(auth, "logout").mockImplementation(async () => {
    identity = null;
    selected = null;
  });
  vi.spyOn(api, "listOrganizations").mockImplementation(
    async () => organizations,
  );
  vi.spyOn(api, "getCurrentOrganization").mockImplementation(
    async () => selected,
  );
  vi.spyOn(api, "selectOrganization").mockImplementation(async (id) => {
    const next = organizations.find((item) => item.id === id);
    if (!next)
      throw new ApiError({
        kind: "http",
        status: 403,
        data: { detail: "Organização indisponível." },
      });
    selected = next;
    return next;
  });
  vi.spyOn(api, "clearOrganization").mockImplementation(async () => {
    selected = null;
  });
});

async function boot() {
  const view = render(<App />);
  await screen.findByRole("region", { name: "Organização" });
  await waitFor(() =>
    expect(
      screen.queryByText("Verificando organização…"),
    ).not.toBeInTheDocument(),
  );
  return view;
}
function choose(id: number) {
  fireEvent.change(
    screen.getByRole("combobox", { name: "Organização disponível" }),
    { target: { value: String(id) } },
  );
  fireEvent.submit(
    screen.getByRole("form", { name: "Selecionar organização" }),
  );
}
function signal() {
  const channel = TestChannel.instances.find((item) => !item.closed);
  if (!channel) throw new Error("Missing test channel");
  act(() => channel.emit({ type: "invalidate", version: 1 }));
}
async function login() {
  fireEvent.change(screen.getByRole("textbox", { name: "E-mail" }), {
    target: { value: "entrada@example.test" },
  });
  fireEvent.change(screen.getByLabelText("Senha"), {
    target: { value: "senha de teste" },
  });
  fireEvent.submit(screen.getByRole("form", { name: "Entrar na conta" }));
  await screen.findByText(user.email);
}

test("contexto fica desativado durante bootstrap, anonimato e login não confirmado", async () => {
  identity = null;
  const read = deferred<auth.UserIdentity | null>();
  vi.mocked(auth.getCurrentUser).mockReturnValueOnce(read.promise);
  render(<App />);
  expect(api.listOrganizations).not.toHaveBeenCalled();
  expect(
    screen.queryByRole("region", { name: "Organização" }),
  ).not.toBeInTheDocument();
  await act(async () => read.resolve(null));
  await screen.findByRole("form");
  expect(api.getCurrentOrganization).not.toHaveBeenCalled();
  const post = deferred<auth.UserIdentity>();
  vi.mocked(auth.login).mockReturnValueOnce(post.promise);
  fireEvent.change(screen.getByRole("textbox", { name: "E-mail" }), {
    target: { value: "pessoa@example.test" },
  });
  fireEvent.change(screen.getByLabelText("Senha"), {
    target: { value: "teste" },
  });
  fireEvent.submit(screen.getByRole("form"));
  await waitFor(() => expect(auth.login).toHaveBeenCalledTimes(1));
  expect(api.listOrganizations).not.toHaveBeenCalled();
});

test("aguarda listagem e current antes de publicar uma organização", async () => {
  const read = deferred<api.AccessibleOrganization | null>();
  vi.mocked(api.getCurrentOrganization).mockReturnValueOnce(read.promise);
  render(<App />);
  expect(await screen.findByText("Verificando organização…")).toBeVisible();
  expect(screen.queryByText(first.name)).not.toBeInTheDocument();
  await act(async () => read.resolve(first));
  expect(
    await screen.findByRole("heading", { name: first.name }),
  ).toBeVisible();
});

test("lista vazia é um estado real, sem seleção fictícia ou botão de cadastro", async () => {
  organizations = [];
  await boot();
  expect(
    screen.getByText("Você não possui organizações acessíveis."),
  ).toBeVisible();
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  expect(api.selectOrganization).not.toHaveBeenCalled();
  expect(
    screen.queryByRole("button", { name: /cadastrar|convidar/i }),
  ).not.toBeInTheDocument();
});

test("uma única organização não é selecionada automaticamente", async () => {
  organizations = [first];
  await boot();
  expect(screen.getByRole("combobox")).toHaveValue("");
  expect(
    screen.getByRole("option", { name: "Selecione uma organização" }),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Usar organização" }),
  ).toBeDisabled();
  fireEvent.submit(screen.getByRole("form"));
  expect(api.selectOrganization).not.toHaveBeenCalled();
});

test.each(["owner", "admin", "member"] as const)(
  "restaura seleção da API e mostra role %s da Membership",
  async (role) => {
    selected = { ...first, role };
    organizations = [selected];
    await boot();
    const label = {
      owner: "Proprietário",
      admin: "Administrador",
      member: "Membro",
    }[role];
    expect(screen.getByRole("heading", { name: first.name })).toBeVisible();
    expect(screen.getByText("Papel: " + label)).toBeVisible();
    expect(api.selectOrganization).not.toHaveBeenCalled();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  },
);

test("seleção MEMBER obtém CSRF, bloqueia duplicidade/logout e aguarda confirmação por leitura", async () => {
  await boot();
  const post = deferred<api.AccessibleOrganization>();
  const confirmation = deferred<api.AccessibleOrganization | null>();
  vi.mocked(api.selectOrganization).mockReturnValueOnce(post.promise);
  vi.mocked(api.getCurrentOrganization).mockReturnValueOnce(
    confirmation.promise,
  );
  fireEvent.change(screen.getByRole("combobox"), {
    target: { value: String(second.id) },
  });
  const form = screen.getByRole("form");
  const leave = screen.getByRole("button", { name: "Sair" });
  act(() => {
    fireEvent.submit(form);
    fireEvent.submit(form);
    fireEvent.click(leave);
  });
  expect(screen.getByText("Alterando organização…")).toBeVisible();
  expect(leave).toBeDisabled();
  expect(screen.queryByText(second.name)).not.toBeInTheDocument();
  await waitFor(() => expect(api.selectOrganization).toHaveBeenCalledTimes(1));
  expect(auth.logout).not.toHaveBeenCalled();
  expect(api.selectOrganization).toHaveBeenCalledWith(
    second.id,
    csrfToken,
    expect.any(AbortSignal),
  );
  expect(
    vi.mocked(auth.getCsrfToken).mock.invocationCallOrder.at(-1),
  ).toBeLessThan(vi.mocked(api.selectOrganization).mock.invocationCallOrder[0]);
  await act(async () => post.resolve(second));
  expect(
    screen.queryByRole("heading", { name: second.name }),
  ).not.toBeInTheDocument();
  await act(async () => confirmation.resolve(second));
  expect(await screen.findByText("Papel: Membro")).toBeVisible();
  expect(screen.getByRole("button", { name: "Limpar seleção" })).toBeEnabled();
  expect(
    screen.getByText(/somente leitura dos recursos empresariais/),
  ).toBeVisible();
});

test("trocar abre um formulário vazio sem PUT; confirmação remove o contexto anterior", async () => {
  selected = first;
  await boot();
  fireEvent.click(screen.getByRole("button", { name: "Trocar organização" }));
  expect(screen.getByRole("combobox")).toHaveValue("");
  expect(api.selectOrganization).not.toHaveBeenCalled();
  choose(second.id);
  expect(screen.queryByText(first.name)).not.toBeInTheDocument();
  expect(screen.queryByText("Papel: Proprietário")).not.toBeInTheDocument();
  expect(
    await screen.findByRole("heading", { name: second.name }),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Trocar organização" }));
  expect(screen.getByRole("combobox")).toHaveValue("");
});

test("limpar usa DELETE do contexto e mantém a identidade e as organizações", async () => {
  selected = second;
  await boot();
  expect(screen.getByText(/mantém você conectado e não exclui/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Limpar seleção" }));
  expect(screen.queryByText(second.name)).not.toBeInTheDocument();
  expect(await screen.findByRole("combobox")).toHaveValue("");
  expect(screen.getByText(user.email)).toBeVisible();
  expect(api.clearOrganization).toHaveBeenCalledWith(
    csrfToken,
    expect.any(AbortSignal),
  );
  expect(auth.logout).not.toHaveBeenCalled();
  expect(
    screen.queryByRole("heading", { name: second.name }),
  ).not.toBeInTheDocument();
});

test.each(["select", "clear"] as const)(
  "%s apresenta o contexto atual se outra aba vencer a escrita",
  async (action) => {
    selected = action === "clear" ? first : null;
    await boot();
    if (action === "clear") {
      vi.mocked(api.clearOrganization).mockImplementationOnce(async () => {
        selected = second;
      });
      fireEvent.click(screen.getByRole("button", { name: "Limpar seleção" }));
    } else {
      vi.mocked(api.selectOrganization).mockImplementationOnce(async () => {
        selected = second;
        return first;
      });
      choose(first.id);
    }
    expect(
      await screen.findByRole("heading", { name: second.name }),
    ).toBeVisible();
    expect(
      screen.getByText(/contexto atual difere da alteração solicitada/),
    ).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: first.name }),
    ).not.toBeInTheDocument();
  },
);

test("falha preparatória de CSRF não envia PUT nem oculta a recuperação", async () => {
  await boot();
  vi.mocked(auth.getCsrfToken).mockRejectedValueOnce(
    new ApiError({ kind: "network" }),
  );
  choose(first.id);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Não foi possível verificar a organização.",
  );
  expect(api.selectOrganization).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Sair" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Verificar contexto" }));
  expect(await screen.findByRole("combobox")).toHaveValue("");
});

test.each(["timeout", "network", "invalid-response"] as const)(
  "resultado incerto %s recupera somente por leitura e não permite logout antecipado",
  async (kind) => {
    await boot();
    vi.mocked(api.selectOrganization).mockImplementationOnce(async () => {
      selected = second;
      throw new ApiError({ kind });
    });
    choose(second.id);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "O resultado da alteração não foi confirmado.",
    );
    expect(screen.queryByText(second.name)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sair" }));
    expect(auth.logout).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Verificar contexto" }));
    expect(
      await screen.findByRole("heading", { name: second.name }),
    ).toBeVisible();
    expect(api.selectOrganization).toHaveBeenCalledTimes(1);
    expect(api.clearOrganization).not.toHaveBeenCalled();
    expect(auth.getCurrentUser).toHaveBeenCalledTimes(2);
  },
);

test("DELETE aceito com confirmação perdida não restaura nome/papel anteriores", async () => {
  selected = first;
  await boot();
  vi.mocked(api.getCurrentOrganization).mockRejectedValueOnce(
    new ApiError({ kind: "network" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Limpar seleção" }));
  expect(await screen.findByRole("alert")).toBeVisible();
  expect(screen.queryByText(first.name)).not.toBeInTheDocument();
  expect(screen.queryByText("Papel: Proprietário")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Verificar contexto" }));
  expect(await screen.findByRole("combobox")).toBeVisible();
  expect(api.clearOrganization).toHaveBeenCalledTimes(1);
});

test("403 de seleção revalida identidade e contexto; não significa logout", async () => {
  await boot();
  vi.mocked(api.selectOrganization).mockRejectedValueOnce(
    new ApiError({
      kind: "http",
      status: 403,
      data: { detail: "Organização indisponível." },
    }),
  );
  choose(first.id);
  expect(await screen.findByText(/A alteração foi recusada/)).toBeVisible();
  expect(screen.getByText(user.email)).toBeVisible();
  expect(auth.getCurrentUser).toHaveBeenCalledTimes(2);
  expect(api.selectOrganization).toHaveBeenCalledTimes(1);
});

test("negação de listagem com sessão ainda válida tem somente uma revalidação", async () => {
  vi.mocked(api.listOrganizations).mockRejectedValue(
    new ApiError({
      kind: "http",
      status: 403,
      data: { detail: "outra recusa" },
    }),
  );
  await boot();
  expect(screen.getByRole("alert")).toBeVisible();
  expect(screen.getByText(user.email)).toBeVisible();
  expect(api.listOrganizations).toHaveBeenCalledTimes(2);
  expect(auth.getCurrentUser).toHaveBeenCalledTimes(2);
});

test("negação seguida de /me anônimo descarta identidade e contexto", async () => {
  vi.mocked(api.listOrganizations).mockImplementation(async () => {
    identity = null;
    throw new ApiError({ kind: "http", status: 403, data: {} });
  });
  render(<App />);
  expect(
    await screen.findByRole("form", { name: "Entrar na conta" }),
  ).toBeVisible();
  expect(screen.queryByText(user.email)).not.toBeInTheDocument();
  expect(
    screen.queryByRole("region", { name: "Organização" }),
  ).not.toBeInTheDocument();
});

test("listagem/current incoerentes repetem uma vez e publicam somente o par coerente", async () => {
  selected = first;
  vi.mocked(api.listOrganizations).mockResolvedValueOnce([second]);
  await boot();
  expect(screen.getByRole("heading", { name: first.name })).toBeVisible();
  expect(api.listOrganizations).toHaveBeenCalledTimes(2);
  expect(api.getCurrentOrganization).toHaveBeenCalledTimes(2);
});

test.each(["missing", "role", "name"] as const)(
  "inconsistência persistente de %s vira erro sem limpar contexto no servidor",
  async (mismatch) => {
    selected = first;
    organizations =
      mismatch === "missing"
        ? [second]
        : [
            {
              ...first,
              ...(mismatch === "role"
                ? { role: "member" as const }
                : { name: "Nome diferente" }),
            },
          ];
    await boot();
    expect(screen.getByRole("alert")).toBeVisible();
    expect(screen.queryByText(first.name)).not.toBeInTheDocument();
    expect(api.listOrganizations).toHaveBeenCalledTimes(2);
    expect(api.clearOrganization).not.toHaveBeenCalled();
  },
);

test("revogação entre abas remove organização e papel, mantendo usuário autenticado", async () => {
  selected = first;
  await boot();
  organizations = [];
  selected = null;
  signal();
  expect(screen.queryByText(first.name)).not.toBeInTheDocument();
  expect(screen.queryByText("Papel: Proprietário")).not.toBeInTheDocument();
  expect(
    await screen.findByText("Você não possui organizações acessíveis."),
  ).toBeVisible();
  expect(screen.getByText(user.email)).toBeVisible();
});

test("aviso entre abas troca identidade/contexto pela API sem aceitar dados da mensagem", async () => {
  selected = first;
  await boot();
  identity = { ...user, id: 8, email: "outra@example.test" };
  organizations = [second];
  selected = second;
  signal();
  expect(screen.queryByText(user.email)).not.toBeInTheDocument();
  expect(screen.queryByText(first.name)).not.toBeInTheDocument();
  expect(await screen.findByText(identity.email)).toBeVisible();
  expect(
    await screen.findByRole("heading", { name: second.name }),
  ).toBeVisible();
  expect(
    TestChannel.instances.every(
      (channel) => channel.postMessage.mock.calls.length === 0,
    ),
  ).toBe(true);
});

test("logout em outra aba elimina identidade/contexto por revalidação", async () => {
  selected = first;
  await boot();
  identity = null;
  selected = null;
  signal();
  expect(screen.queryByText(first.name)).not.toBeInTheDocument();
  expect(
    await screen.findByRole("form", { name: "Entrar na conta" }),
  ).toBeVisible();
  expect(auth.logout).not.toHaveBeenCalled();
});

test("aviso durante PUT espera a mutação e exige confirmação posterior da identidade", async () => {
  await boot();
  const post = deferred<api.AccessibleOrganization>();
  vi.mocked(api.selectOrganization).mockReturnValueOnce(post.promise);
  choose(first.id);
  await waitFor(() => expect(api.selectOrganization).toHaveBeenCalledTimes(1));
  signal();
  expect(auth.getCurrentUser).toHaveBeenCalledTimes(1);
  expect(api.listOrganizations).toHaveBeenCalledTimes(1);
  selected = second;
  await act(async () => post.resolve(first));
  expect(
    await screen.findByRole("heading", { name: second.name }),
  ).toBeVisible();
  expect(auth.getCurrentUser).toHaveBeenCalledTimes(2);
  expect(api.selectOrganization).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("Papel: Proprietário")).not.toBeInTheDocument();
});

test("aviso em recuperação de mutação incerta provoca apenas leituras", async () => {
  await boot();
  vi.mocked(api.selectOrganization).mockImplementationOnce(async () => {
    selected = second;
    throw new ApiError({ kind: "timeout" });
  });
  choose(second.id);
  await screen.findByRole("alert");
  signal();
  expect(
    await screen.findByRole("heading", { name: second.name }),
  ).toBeVisible();
  expect(api.selectOrganization).toHaveBeenCalledTimes(1);
  expect(auth.logout).not.toHaveBeenCalled();
});

test("fallback agrupa foco/visibilidade e mantém formulário anônimo em edição", async () => {
  identity = null;
  vi.stubGlobal("BroadcastChannel", undefined);
  render(<App />);
  const form = await screen.findByRole("form");
  const email = screen.getByRole("textbox", { name: "E-mail" });
  const password = screen.getByLabelText("Senha");
  fireEvent.change(email, { target: { value: "em-edicao@example.test" } });
  fireEvent.change(password, { target: { value: "ainda editando" } });
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
  act(() => {
    window.dispatchEvent(new Event("focus"));
    document.dispatchEvent(new Event("visibilitychange"));
    window.dispatchEvent(new Event("focus"));
  });
  expect(screen.getByRole("form")).toBe(form);
  await waitFor(() => expect(auth.getCurrentUser).toHaveBeenCalledTimes(2));
  expect(email).toHaveValue("em-edicao@example.test");
  expect(password).toHaveValue("ainda editando");
  expect(api.listOrganizations).not.toHaveBeenCalled();
  expect(auth.login).not.toHaveBeenCalled();
});

test("fallback por foco revalida contexto sem BroadcastChannel", async () => {
  vi.stubGlobal("BroadcastChannel", undefined);
  selected = first;
  await boot();
  selected = second;
  act(() => window.dispatchEvent(new Event("focus")));
  expect(screen.queryByText(first.name)).not.toBeInTheDocument();
  expect(
    await screen.findByRole("heading", { name: second.name }),
  ).toBeVisible();
});

test("leitura superada por foco não substitui seleção mais recente mesmo ignorando abort", async () => {
  const old = deferred<api.AccessibleOrganization | null>();
  vi.mocked(api.getCurrentOrganization).mockReturnValueOnce(old.promise);
  render(<App />);
  await screen.findByText("Verificando organização…");
  signal();
  await screen.findByRole("combobox");
  choose(second.id);
  await screen.findByRole("heading", { name: second.name });
  await act(async () => old.resolve(first));
  expect(screen.getByRole("heading", { name: second.name })).toBeVisible();
  expect(screen.queryByText(first.name)).not.toBeInTheDocument();
});

test("falha na criação do canal mantém fallback e aba oculta não dispara leitura", async () => {
  vi.stubGlobal(
    "BroadcastChannel",
    class {
      constructor() {
        throw new Error("Channel unavailable");
      }
    },
  );
  selected = first;
  await boot();
  const visibility = vi
    .spyOn(document, "visibilityState", "get")
    .mockReturnValue("hidden");
  act(() => document.dispatchEvent(new Event("visibilitychange")));
  expect(auth.getCurrentUser).toHaveBeenCalledTimes(1);
  selected = second;
  visibility.mockReturnValue("visible");
  act(() => document.dispatchEvent(new Event("visibilitychange")));
  expect(
    await screen.findByRole("heading", { name: second.name }),
  ).toBeVisible();
  expect(auth.getCurrentUser).toHaveBeenCalledTimes(2);
});

test("resposta antiga não reaparece após logout e novo login do mesmo usuário", async () => {
  const old = deferred<api.AccessibleOrganization | null>();
  vi.mocked(api.getCurrentOrganization).mockReturnValueOnce(old.promise);
  render(<App />);
  await screen.findByText("Verificando organização…");
  const oldSignal = vi.mocked(api.getCurrentOrganization).mock.calls[0][0];
  fireEvent.click(screen.getByRole("button", { name: "Sair" }));
  await screen.findByRole("form", { name: "Entrar na conta" });
  expect(oldSignal?.aborted).toBe(true);
  await login();
  expect(await screen.findByRole("combobox")).toBeVisible();
  choose(second.id);
  await screen.findByRole("heading", { name: second.name });
  await act(async () => old.resolve(first));
  expect(screen.getByRole("heading", { name: second.name })).toBeVisible();
  expect(screen.queryByText(first.name)).not.toBeInTheDocument();
});

test("StrictMode não duplica listeners/canal e cleanup invalida respostas tardias", async () => {
  const pending = deferred<api.AccessibleOrganization | null>();
  vi.mocked(api.getCurrentOrganization).mockReturnValue(pending.promise);
  const view = render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
  await screen.findByText("Verificando organização…");
  expect(
    TestChannel.instances.filter((channel) => !channel.closed),
  ).toHaveLength(1);
  expect(api.selectOrganization).not.toHaveBeenCalled();
  const count = vi.mocked(api.listOrganizations).mock.calls.length;
  view.unmount();
  expect(TestChannel.instances.every((channel) => channel.closed)).toBe(true);
  act(() => {
    window.dispatchEvent(new Event("focus"));
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await act(async () => pending.resolve(first));
  expect(api.listOrganizations).toHaveBeenCalledTimes(count);
  expect(screen.queryByText(first.name)).not.toBeInTheDocument();
});

test.each([
  null,
  {},
  "invalidate",
  { type: "invalidate", version: 2 },
  { type: "invalidate", version: 1, organization: first },
])(
  "mensagem inválida %j não fornece autoridade nem provoca leitura",
  async (message) => {
    await boot();
    const channel = TestChannel.instances.find((item) => !item.closed);
    act(() => channel?.emit(message));
    expect(auth.getCurrentUser).toHaveBeenCalledTimes(1);
    expect(api.listOrganizations).toHaveBeenCalledTimes(1);
  },
);

test("duas abas da mesma origem recebem só invalidação e consultam o contexto real", async () => {
  render(
    <>
      <div data-testid="first-tab">
        <App />
      </div>
      <div data-testid="second-tab">
        <App />
      </div>
    </>,
  );
  await waitFor(() => expect(screen.getAllByRole("combobox")).toHaveLength(2));
  const tab = within(screen.getByTestId("first-tab"));
  fireEvent.change(tab.getByRole("combobox"), {
    target: { value: String(second.id) },
  });
  fireEvent.submit(tab.getByRole("form"));
  await waitFor(() =>
    expect(screen.getAllByRole("heading", { name: second.name })).toHaveLength(
      2,
    ),
  );
  const messages = TestChannel.instances.flatMap((channel) =>
    channel.postMessage.mock.calls.map(([data]) => data),
  );
  expect(messages).toEqual([{ type: "invalidate", version: 1 }]);
  expect(api.selectOrganization).toHaveBeenCalledTimes(1);
});
