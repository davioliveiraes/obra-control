export const csrfToken = "a".repeat(64);
export const user = {
  id: 7,
  email: "pessoa@example.test",
  first_name: "Pessoa",
  last_name: "Teste",
};
export const anonymousPayload = {
  detail: "As credenciais de autenticação não foram fornecidas.",
};

export function jsonResponse(data: unknown, status = 200) {
  return Response.json(data, { status });
}

export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}
