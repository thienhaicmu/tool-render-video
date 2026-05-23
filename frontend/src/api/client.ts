/**
 * Base fetch wrapper with typed request/response and centralized error handling.
 *
 * BASE_URL resolution:
 *   - In production (Electron or same-origin served by FastAPI): empty string → same-origin requests.
 *   - In development: Vite proxy intercepts /api/* → 127.0.0.1:8000, so empty string also works.
 *   - Override with VITE_API_BASE_URL env var for custom setups (e.g., remote backend).
 */

export const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? ''

// ── ApiError ──────────────────────────────────────────────────────────────────

export class ApiError extends Error {
  readonly status: number
  readonly detail: string | unknown

  constructor(status: number, detail: string | unknown, message?: string) {
    super(message ?? `API error ${status}: ${JSON.stringify(detail)}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

// ── Core fetch wrapper ────────────────────────────────────────────────────────

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: unknown = res.statusText
    try {
      const body = await res.json()
      // FastAPI returns {detail: ...} for validation errors and HTTPExceptions
      detail = body?.detail ?? body
    } catch {
      // non-JSON error body — keep statusText
    }
    throw new ApiError(res.status, detail)
  }
  // 204 No Content
  if (res.status === 204) {
    return undefined as unknown as T
  }
  return res.json() as Promise<T>
}

export async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const url = path.startsWith('http') ? path : `${BASE_URL}${path}`
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers ?? {}),
    },
  })
  return handleResponse<T>(res)
}

export async function apiFetchFormData<T>(
  path: string,
  body: FormData,
  options?: Omit<RequestInit, 'body' | 'method'>,
): Promise<T> {
  const url = path.startsWith('http') ? path : `${BASE_URL}${path}`
  const res = await fetch(url, {
    method: 'POST',
    body,
    ...options,
    // Do NOT set Content-Type — browser sets multipart/form-data + boundary automatically
  })
  return handleResponse<T>(res)
}
