/**
 * dashboard/src/lib/api.ts
 *
 * Phase 9. Same story as lib/keycloak.ts — hooks/useIngestionJobs.ts and
 * hooks/useRAGQuery.ts have imported `{ api }` from this path since
 * Phase 1; this file never existed.
 *
 * Error envelope below is copied verbatim from
 * api-gateway/src/middleware/rate_limit.py's rate_limit_exceeded_handler
 * and main.py's 404/500 handlers — every error response in this API
 * shares one shape: `{ error: { code, message, request_id?,
 * retry_after_seconds? } }`. There is no separate "validation error"
 * shape to special-case here; FastAPI's default 422 body doesn't match
 * this envelope, but no route in this API currently returns anything a
 * dashboard form couldn't already reject client-side first (Pydantic
 * field constraints mirrored in the Zod-free manual validation in
 * NewJobForm.tsx / QueryForm.tsx), so it isn't handled specially either
 * — getApiErrorMessage() below falls back to axios's own message for
 * any response that isn't in the `{ error: {...} }` shape.
 */
import axios, { AxiosError } from 'axios'
import { getValidToken, logout } from './keycloak'

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    request_id?: string | null
    retry_after_seconds?: number | null
  }
}

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/v1',
  timeout: 30_000,
})

api.interceptors.request.use(async (config) => {
  const token = await getValidToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err: AxiosError<ApiErrorBody>) => {
    // 401: the backend's KeycloakJWTMiddleware rejected or never saw a
    // credential. When auth is enabled, a live session should have been
    // attached by the request interceptor above — a 401 here almost
    // always means the refresh token itself expired (getValidToken()
    // already tried once and gave up). Re-running the full Keycloak
    // login flow is the only real recovery; when auth is disabled this
    // branch shouldn't fire at all (the backend doesn't require a
    // credential), so it's safe to gate on isAuthEnabled implicitly via
    // logout()'s own no-op-when-disabled guard.
    if (err.response?.status === 401) {
      logout()
    }
    return Promise.reject(err)
  },
)

/** True when `err` is an axios error carrying this API's error envelope. */
export function isApiError(err: unknown): err is AxiosError<ApiErrorBody> {
  return axios.isAxiosError(err) && typeof err.response?.data === 'object' && err.response?.data !== null && 'error' in (err.response.data as object)
}

/**
 * Extracts a human-readable message from any error a hook/component
 * might catch from an `api` call — the `{ error: {...} }` envelope when
 * present, a generic network-failure message otherwise. Rate-limit
 * errors (429) get their retry_after_seconds appended, since "Rate limit
 * exceeded" alone doesn't tell the person anything actionable — matches
 * doc 09's own example envelope, which carries that field specifically
 * so callers can surface it.
 */
export function getApiErrorMessage(err: unknown): string {
  if (isApiError(err)) {
    const { message, retry_after_seconds } = err.response!.data.error
    if (typeof retry_after_seconds === 'number') {
      return `${message} — retry in ${retry_after_seconds}s`
    }
    return message
  }
  if (axios.isAxiosError(err)) {
    if (err.code === 'ECONNABORTED') return 'Request timed out — please try again.'
    if (!err.response) return 'Could not reach the API — check your connection.'
    return `Request failed (${err.response.status})`
  }
  return err instanceof Error ? err.message : 'An unexpected error occurred'
}

/** Structured accessor for the fields a 429 handler needs specifically. */
export function getRetryAfterSeconds(err: unknown): number | null {
  if (isApiError(err) && err.response?.status === 429) {
    return err.response.data.error.retry_after_seconds ?? null
  }
  return null
}
