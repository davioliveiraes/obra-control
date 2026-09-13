import { useId, useRef } from "react";
import type { SubmitEvent } from "react";
import type { LoginCredentials, LoginProblem } from "./api";

interface LoginFormProps {
  busy: boolean;
  problem?: LoginProblem;
  onLogin: (credentials: LoginCredentials) => Promise<void>;
}

export function LoginForm({ busy, problem, onLogin }: LoginFormProps) {
  const id = useId();
  const email = useRef<HTMLInputElement>(null);
  const password = useRef<HTMLInputElement>(null);
  const submitting = useRef(false);

  const submit = async (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || submitting.current || !event.currentTarget.reportValidity())
      return;
    const emailInput = email.current;
    const passwordInput = password.current;
    if (!emailInput || !passwordInput) return;
    submitting.current = true;
    try {
      await onLogin({ email: emailInput.value, password: passwordInput.value });
    } finally {
      passwordInput.value = "";
      submitting.current = false;
    }
  };

  return (
    <form aria-label="Entrar na conta" aria-busy={busy} onSubmit={submit}>
      {problem && <p role="alert">{problem.message}</p>}
      <div className="field">
        <label htmlFor={id + "-email"}>E-mail</label>
        <input
          ref={email}
          id={id + "-email"}
          type="email"
          name="email"
          autoComplete="username"
          required
          disabled={busy}
          aria-invalid={Boolean(problem?.fields?.email)}
          aria-describedby={
            problem?.fields?.email ? id + "-email-error" : undefined
          }
        />
        {problem?.fields?.email && (
          <p id={id + "-email-error"} className="field-error">
            {problem.fields.email}
          </p>
        )}
      </div>
      <div className="field">
        <label htmlFor={id + "-password"}>Senha</label>
        <input
          ref={password}
          id={id + "-password"}
          type="password"
          name="password"
          autoComplete="current-password"
          required
          disabled={busy}
          aria-invalid={Boolean(problem?.fields?.password)}
          aria-describedby={
            problem?.fields?.password ? id + "-password-error" : undefined
          }
        />
        {problem?.fields?.password && (
          <p id={id + "-password-error"} className="field-error">
            {problem.fields.password}
          </p>
        )}
      </div>
      <button type="submit" disabled={busy}>
        {busy ? "Entrando…" : "Entrar"}
      </button>
    </form>
  );
}
