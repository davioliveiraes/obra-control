import { SessionStatus } from "../features/auth/SessionStatus";
import { useAuthSession } from "../features/auth/useAuthSession";
import { useSessionInvalidation } from "../features/auth/useSessionInvalidation";
import { AuthenticatedSession } from "../features/organizations/AuthenticatedSession";

export default function App() {
  const session = useAuthSession();
  const notify = useSessionInvalidation(
    session.invalidate,
    session.mutationRevision,
  );
  const { state, verify, login, logout } = session;

  return (
    <main>
      <p className="stage">Etapa F5 · Contexto de organização</p>
      <h1>ObraControl</h1>
      <p className="description">Gestão de obras para empresas.</p>
      {state.status === "authenticated" ? (
        <AuthenticatedSession
          key={state.user.id}
          session={session}
          notify={notify}
        />
      ) : (
        <SessionStatus
          state={state}
          onVerify={verify}
          onLogin={login}
          onLogout={logout}
        />
      )}
    </main>
  );
}
