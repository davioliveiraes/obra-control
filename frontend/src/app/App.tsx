import { SessionStatus } from "../features/auth/SessionStatus";
import { useAuthSession } from "../features/auth/useAuthSession";

export default function App() {
  const { state, verify, login, logout } = useAuthSession();

  return (
    <main>
      <p className="stage">Etapa F3 · Acesso por sessão</p>
      <h1>ObraControl</h1>
      <p className="description">Gestão de obras para empresas.</p>
      <SessionStatus
        state={state}
        onVerify={verify}
        onLogin={login}
        onLogout={logout}
      />
    </main>
  );
}
