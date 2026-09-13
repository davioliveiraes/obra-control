import { LoginForm } from "./LoginForm";
import type { LoginCredentials } from "./api";
import type { SessionState } from "./useAuthSession";

interface SessionStatusProps {
  state: SessionState;
  onVerify: () => void;
  onLogin: (credentials: LoginCredentials) => Promise<void>;
  onLogout: () => Promise<void>;
  logoutDisabled?: boolean;
}

const errors = {
  read: "Não foi possível verificar a sessão. Tente novamente.",
  "login-preparation":
    "Não foi possível preparar a entrada. Nenhum login foi enviado.",
  "logout-preparation":
    "Não foi possível preparar a saída. Nenhum logout foi enviado.",
  "login-unconfirmed":
    "Não foi possível confirmar a entrada. Verifique a sessão antes de tentar novamente.",
  "logout-unconfirmed":
    "Não foi possível confirmar a saída. Verifique a sessão antes de tentar novamente.",
  "logout-rejected":
    "A saída foi recusada. Verifique a sessão antes de tentar novamente.",
};

export function SessionStatus({
  state,
  onVerify,
  onLogin,
  onLogout,
  logoutDisabled = false,
}: SessionStatusProps) {
  if (state.status === "error") {
    return (
      <section aria-label="Sessão">
        <p role="alert">{errors[state.reason]}</p>
        <button type="button" onClick={onVerify}>
          {state.reason === "read" ? "Tentar novamente" : "Verificar sessão"}
        </button>
      </section>
    );
  }
  if (state.status === "anonymous" || state.status === "signing-in") {
    return (
      <section aria-label="Sessão">
        <p role="status">
          {state.status === "anonymous"
            ? "Nenhuma sessão autenticada"
            : "Entrando…"}
        </p>
        <LoginForm
          busy={state.status === "signing-in"}
          problem={state.status === "anonymous" ? state.problem : undefined}
          onLogin={onLogin}
        />
      </section>
    );
  }
  if (state.status === "authenticated") {
    return (
      <section aria-label="Sessão">
        <p role="status">
          Sessão autenticada: <strong>{state.user.email}</strong>
        </p>
        {state.logoutUnconfirmed && (
          <p role="alert">
            A sessão continua autenticada. A saída não foi confirmada.
          </p>
        )}
        <button type="button" onClick={onLogout} disabled={logoutDisabled}>
          Sair
        </button>
        <p className="modules-note">Os módulos ainda não estão disponíveis.</p>
      </section>
    );
  }
  return (
    <section aria-label="Sessão" aria-busy="true">
      <p role="status">
        {state.status === "signing-out" ? "Saindo…" : "Verificando sessão…"}
      </p>
    </section>
  );
}
