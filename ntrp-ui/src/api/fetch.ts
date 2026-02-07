export interface ApiError extends Error {
  status?: number;
  statusText?: string;
  isNetworkError: boolean;
  isTimeout: boolean;
}

export interface FetchOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
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

  // Create timeout controller
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  // Combine with external signal if provided
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
      // Try to parse error message from response
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

    // Handle empty responses
    const contentType = response.headers.get("content-type");
    if (!contentType?.includes("application/json")) {
      return undefined as T;
    }

    return await response.json();
  } catch (error) {
    clearTimeout(timeoutId);

    if (error instanceof Error) {
      // Handle abort (timeout)
      if (error.name === "AbortError") {
        throw createApiError(`Request timed out after ${timeout}ms`, { isTimeout: true });
      }

      // Handle network errors
      if (error.name === "TypeError" && error.message.includes("fetch")) {
        throw createApiError("Network error: Unable to reach server", { isNetworkError: true });
      }

      // Re-throw ApiErrors as-is
      if ((error as ApiError).isNetworkError !== undefined) {
        throw error;
      }
    }

    // Wrap unknown errors
    throw createApiError(`Unexpected error: ${error}`, { isNetworkError: true });
  }
}

export const api = {
  get: <T>(url: string, options?: Omit<FetchOptions, "method" | "body">) =>
    apiFetch<T>(url, { ...options, method: "GET" }),

  post: <T>(url: string, body?: unknown, options?: Omit<FetchOptions, "method" | "body">) =>
    apiFetch<T>(url, { ...options, method: "POST", body }),

  patch: <T>(url: string, body?: unknown, options?: Omit<FetchOptions, "method" | "body">) =>
    apiFetch<T>(url, { ...options, method: "PATCH", body }),

  delete: <T>(url: string, options?: Omit<FetchOptions, "method" | "body">) =>
    apiFetch<T>(url, { ...options, method: "DELETE" }),
};
