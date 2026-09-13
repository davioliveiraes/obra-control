const API_BASE = "/api/v1/";
const REQUEST_TIMEOUT_MS = 15_000;

export type ApiFailure =
  | { kind: "http"; status: number; data: unknown }
  | {
      kind:
        | "network"
        | "timeout"
        | "aborted"
        | "invalid-response"
        | "invalid-request";
    };

export class ApiError extends Error {
  readonly failure: ApiFailure;

  constructor(failure: ApiFailure) {
    super("Não foi possível concluir a requisição à API.");
    this.name = "ApiError";
    this.failure = failure;
  }
}

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface RequestOptions {
  method?: Method;
  json?: unknown;
  csrfToken?: string;
  signal?: AbortSignal;
  cache?: RequestCache;
  expectedStatus?: number;
}

function internalPath(path: string): string {
  try {
    const hasControl = (value: string) =>
      [...value].some((character) => {
        const code = character.charCodeAt(0);
        return code < 32 || code === 127;
      });
    if (!path.startsWith(API_BASE) || /[\\\s]/u.test(path)) {
      throw new Error();
    }
    const url = new URL(path, window.location.origin);
    // Reject encoded separators and double encoding before a server can decode them.
    const decoded = decodeURIComponent(url.pathname);
    if (
      url.origin !== window.location.origin ||
      url.hash ||
      hasControl(path) ||
      hasControl(decoded) ||
      !url.pathname.startsWith(API_BASE) ||
      /%(?:2f|5c|25)/i.test(url.pathname) ||
      /[\\\s]/u.test(decoded) ||
      !new URL(decoded, window.location.origin).pathname.startsWith(API_BASE)
    ) {
      throw new Error();
    }
    return url.pathname + url.search;
  } catch {
    throw new ApiError({ kind: "invalid-request" });
  }
}

export async function request(
  path: string,
  options: RequestOptions = {},
): Promise<unknown> {
  const url = internalPath(path);
  const method = options.method ?? "GET";
  const unsafe = ["POST", "PUT", "PATCH", "DELETE"].includes(method);
  if (
    (!unsafe && method !== "GET") ||
    (method === "GET" && options.json !== undefined) ||
    (unsafe &&
      (typeof options.csrfToken !== "string" ||
        !/^[a-zA-Z0-9]+$/.test(options.csrfToken)))
  ) {
    throw new ApiError({ kind: "invalid-request" });
  }
  if (options.signal?.aborted) {
    throw new ApiError({ kind: "aborted" });
  }

  const headers = new Headers({ Accept: "application/json" });
  let body: string | undefined;
  if (options.json !== undefined) {
    try {
      body = JSON.stringify(options.json);
      if (body === undefined) throw new Error();
    } catch {
      throw new ApiError({ kind: "invalid-request" });
    }
    headers.set("Content-Type", "application/json");
  }
  if (unsafe && options.csrfToken) {
    headers.set("X-CSRFToken", options.csrfToken);
  }

  const controller = new AbortController();
  let interruption: "timeout" | "aborted" | undefined;
  let onAbort = () => {};
  let timer: ReturnType<typeof setTimeout> | undefined;
  const interrupted = new Promise<never>((_, reject) => {
    const stop = (kind: "timeout" | "aborted") => {
      interruption ??= kind;
      controller.abort();
      reject(new ApiError({ kind: interruption }));
    };
    onAbort = () => stop("aborted");
    options.signal?.addEventListener("abort", onAbort, { once: true });
    timer = setTimeout(() => stop("timeout"), REQUEST_TIMEOUT_MS);
  });

  const perform = async (): Promise<unknown> => {
    const response = await fetch(url, {
      method,
      headers,
      body,
      credentials: "same-origin",
      mode: "same-origin",
      redirect: "error",
      signal: controller.signal,
      cache: options.cache,
    });
    if (response.redirected || response.type === "opaqueredirect") {
      throw new ApiError({ kind: "invalid-response" });
    }
    if (
      response.ok &&
      options.expectedStatus !== undefined &&
      response.status !== options.expectedStatus
    ) {
      throw new ApiError({ kind: "invalid-response" });
    }
    if (response.status === 204) return undefined;
    const contentType = response.headers
      .get("Content-Type")
      ?.split(";")[0]
      .trim()
      .toLowerCase();
    const isJson =
      contentType === "application/json" ||
      (contentType?.startsWith("application/") &&
        contentType.endsWith("+json"));
    if (!isJson) {
      if (!response.ok)
        throw new ApiError({
          kind: "http",
          status: response.status,
          data: undefined,
        });
      throw new ApiError({ kind: "invalid-response" });
    }
    let data: unknown;
    try {
      data = JSON.parse(await response.text());
    } catch {
      if (interruption) throw new ApiError({ kind: interruption });
      if (!response.ok)
        throw new ApiError({
          kind: "http",
          status: response.status,
          data: undefined,
        });
      throw new ApiError({ kind: "invalid-response" });
    }
    if (!response.ok)
      throw new ApiError({ kind: "http", status: response.status, data });
    return data;
  };

  try {
    // Racing also handles test doubles that ignore AbortSignal.
    return await Promise.race([perform(), interrupted]);
  } catch (error) {
    if (interruption) throw new ApiError({ kind: interruption });
    if (error instanceof ApiError) throw error;
    throw new ApiError({ kind: "network" });
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", onAbort);
    controller.abort();
  }
}
