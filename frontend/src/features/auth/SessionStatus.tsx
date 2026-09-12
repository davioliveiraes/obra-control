import type { SessionState } from "./useSessionBootstrap";

interface SessionStatusProps {
  state: SessionState;
  onRetry: () => void;
}

export function SessionStatus({ state, onRetry }: SessionStatusProps) {
  if (state.status === "error") {
    return (
      <section aria-label="Sessão">
        <p role="alert">
          Não foi possível verificar a sessão. Tente novamente.
        </p>
        <button type="button" onClick={onRetry}>
          Tentar novamente
        </button>
      </section>
    );
  }
  return (
    <section aria-label="Sessão" aria-busy={state.status === "checking"}>
      <p role="status">
        {state.status === "checking" && "Verificando sessão…"}
        {state.status === "anonymous" && "Nenhuma sessão autenticada"}
        {state.status === "authenticated" && (
          <>
            Sessão autenticada: <strong>{state.user.email}</strong>
          </>
        )}
      </p>
    </section>
  );
}
