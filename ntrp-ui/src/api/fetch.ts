interface ApiError extends Error {
  status?: number;
  statusText?: string;
  isNetworkError: boolean;
  isTimeout: boolean;
}

interface FetchOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  timeout?: number;
  signal?: AbortSignal;
}

const DEFAULT_TIMEOUT = 30000; // 30 seconds

function createApiError(
  message: string,
  options: { status?: number; statusText?: string; isNetworkError?: boolean; isTimeout?: boolean } = {}
): ApiError {
  const error = new Error(message) as ApiError;
  error.name = "ApiError";
  error.status = options.status;
  error.statusText = options.statusText;
  error.isNetworkError = options.isNetworkError ?? false;
  error.isTimeout = options.isTimeout ?? false;
  return error;
}

async function apiFetch<T>(url: string, options: FetchOptions = {}): Promise<T> {
  const { method = "GET", body, timeout = DEFAULT_TIMEOUT, signal } = options;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  const combinedSignal = signal
    ? AbortSignal.any([controller.signal, signal])
    : controller.signal;

  try {
    const response = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: combinedSignal,
    });

    clearTimeout(timeoutId);

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
    clearTimeout(timeoutId);

    if (error instanceof Error) {
      if (error.name === "AbortError") {
        throw createApiError(`Request timed out after ${timeout}ms`, { isTimeout: true });
      }

      if (error.name === "TypeError" && error.message.includes("fetch")) {
        throw createApiError("Network error: Unable to reach server", { isNetworkError: true });
      }

      if ((error as ApiError).isNetworkError !== undefined) {
        throw error;
      }
    }

    throw createApiError(`Unexpected error: ${error}`, { isNetworkError: true });
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
