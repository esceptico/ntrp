export type ApiErrorKind = "http" | "network" | "timeout";

export interface ApiError extends Error {
  kind: ApiErrorKind;
  status?: number;
  statusText?: string;
}

interface FetchOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  timeout?: number;
  signal?: AbortSignal;
}

const DEFAULT_TIMEOUT = 30000; // 30 seconds

let _apiKey = "";

export function setApiKey(key: string) {
  _apiKey = key;
}

export function getApiKey(): string {
  return _apiKey;
}

function createApiError(
  message: string,
  options: { kind?: ApiErrorKind; status?: number; statusText?: string } = {}
): ApiError {
  const error = new Error(message) as ApiError;
  error.name = "ApiError";
  error.kind = options.kind ?? "http";
  error.status = options.status;
  error.statusText = options.statusText;
  return error;
}

async function apiFetch<T>(url: string, options: FetchOptions = {}): Promise<T> {
  const { method = "GET", body, timeout = DEFAULT_TIMEOUT, signal } = options;

  const controller = new AbortController();
  const timeoutId = timeout > 0 ? setTimeout(() => controller.abort(), timeout) : null;

  const combinedSignal = signal
    ? AbortSignal.any([controller.signal, signal])
    : controller.signal;

  try {
    const headers: Record<string, string> = {};
    if (body) headers["Content-Type"] = "application/json";
    if (_apiKey) headers["Authorization"] = `Bearer ${_apiKey}`;

    const response = await fetch(url, {
      method,
      headers: Object.keys(headers).length > 0 ? headers : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: combinedSignal,
    });

    if (timeoutId) clearTimeout(timeoutId);

    if (!response.ok) {
      let errorMessage = `Request failed: ${response.status}`;
      try {
        const errorBody = await response.json();
        if (errorBody.detail) {
          errorMessage = errorBody.detail;
        } else if (errorBody.message) {
          errorMessage = errorBody.message;
        }
      } catch {
        // Ignore JSON parse errors
      }

      throw createApiError(errorMessage, {
        status: response.status,
        statusText: response.statusText,
      });
    }

    const contentType = response.headers.get("content-type");
    if (!contentType?.includes("application/json")) {
      return undefined as T;
    }

    return await response.json();
  } catch (error) {
    if (timeoutId) clearTimeout(timeoutId);

    if (error instanceof Error) {
      if (error.name === "AbortError") {
        if (controller.signal.aborted) {
          throw createApiError(`Request timed out after ${timeout}ms`, { kind: "timeout" });
        }
        throw error; // External abort — propagate as-is
      }

      if (error.name === "TypeError" && error.message.includes("fetch")) {
        throw createApiError("Network error: Unable to reach server", { kind: "network" });
      }

      if ((error as ApiError).kind !== undefined) {
        throw error;
      }
    }

    throw createApiError(`Unexpected error: ${error}`, { kind: "network" });
  }
}

export const api = {
  get: <T>(url: string, options?: Omit<FetchOptions, "method" | "body">) =>
    apiFetch<T>(url, { ...options, method: "GET" }),

  post: <T>(url: string, body?: unknown, options?: Omit<FetchOptions, "method" | "body">) =>
    apiFetch<T>(url, { ...options, method: "POST", body }),

  put: <T>(url: string, body?: unknown, options?: Omit<FetchOptions, "method" | "body">) =>
    apiFetch<T>(url, { ...options, method: "PUT", body }),

  patch: <T>(url: string, body?: unknown, options?: Omit<FetchOptions, "method" | "body">) =>
    apiFetch<T>(url, { ...options, method: "PATCH", body }),

  delete: <T>(url: string, options?: Omit<FetchOptions, "method" | "body">) =>
    apiFetch<T>(url, { ...options, method: "DELETE" }),
};
