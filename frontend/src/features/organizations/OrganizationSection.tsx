import { useId, useState } from "react";
import type { SubmitEvent } from "react";
import type { OrganizationRole } from "./api";
import type { OrganizationState } from "./useOrganizationContext";

const roles: Record<OrganizationRole, string> = {
  owner: "Proprietário",
  admin: "Administrador",
  member: "Membro",
};

interface Props {
  state: OrganizationState;
  onSelect: (id: number) => Promise<void>;
  onClear: () => Promise<void>;
  onVerify: () => void;
}

export function OrganizationSection({
  state,
  onSelect,
  onClear,
  onVerify,
}: Props) {
  const id = useId();
  const [choice, setChoice] = useState("");
  const [editing, setEditing] = useState(false);
  const submit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (choice && event.currentTarget.reportValidity())
      void onSelect(Number(choice));
  };
  return (
    <section aria-labelledby={id + "-heading"} className="organization-section">
      <h2 id={id + "-heading"}>Organização</h2>
      {(state.status === "checking" || state.status === "changing") && (
        <p role="status">
          {state.status === "changing"
            ? "Alterando organização…"
            : "Verificando organização…"}
        </p>
      )}
      {state.status === "error" && (
        <>
          <p role="alert">
            {state.uncertain
              ? "O resultado da alteração não foi confirmado. Verifique o contexto antes de continuar."
              : "Não foi possível verificar a organização. Tente novamente."}
          </p>
          <button type="button" onClick={onVerify}>
            Verificar contexto
          </button>
        </>
      )}
      {"notice" in state && state.notice && <p role="status">{state.notice}</p>}
      {state.status === "empty" && (
        <>
          <p role="status">Você não possui organizações acessíveis.</p>
          <button type="button" onClick={onVerify}>
            Verificar contexto
          </button>
        </>
      )}
      {state.status === "active" && (
        <>
          <p>Organização ativa</p>
          <h3>{state.current.name}</h3>
          <p>Papel: {roles[state.current.role]}</p>
          {state.current.role === "member" && (
            <p>
              Seu papel permite somente leitura dos recursos empresariais. Você
              pode selecionar ou limpar a organização.
            </p>
          )}
          {!editing && (
            <button type="button" onClick={() => setEditing(true)}>
              Trocar organização
            </button>
          )}
          <p id={id + "-clear"}>
            Limpar seleção mantém você conectado e não exclui a organização.
          </p>
          <button
            type="button"
            aria-describedby={id + "-clear"}
            onClick={() => void onClear()}
          >
            Limpar seleção
          </button>
        </>
      )}
      {(state.status === "choosing" ||
        (state.status === "active" && editing)) && (
        <form aria-label="Selecionar organização" onSubmit={submit}>
          <div className="field">
            <label htmlFor={id + "-select"}>Organização disponível</label>
            <select
              id={id + "-select"}
              name="organization_id"
              required
              value={choice}
              onChange={(event) => setChoice(event.target.value)}
            >
              <option value="">Selecione uma organização</option>
              {state.organizations.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          <div className="actions">
            <button type="submit" disabled={!choice}>
              Usar organização
            </button>
            {state.status === "active" && (
              <button
                type="button"
                onClick={() => {
                  setEditing(false);
                  setChoice("");
                }}
              >
                Cancelar troca
              </button>
            )}
          </div>
        </form>
      )}
    </section>
  );
}
