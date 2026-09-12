import { SessionStatus } from "../features/auth/SessionStatus";
import { useSessionBootstrap } from "../features/auth/useSessionBootstrap";

export default function App() {
  const { state, retry } = useSessionBootstrap();

  return (
    <main>
      <p className="stage">Etapa F2 · Integração inicial</p>
      <h1>ObraControl</h1>
      <p className="description">Gestão de obras para empresas.</p>
      <SessionStatus state={state} onRetry={retry} />
    </main>
  );
}
