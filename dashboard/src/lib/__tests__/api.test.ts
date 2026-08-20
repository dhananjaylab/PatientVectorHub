import { describe, expect, it, vi } from 'vitest'
import { AxiosError, AxiosHeaders } from 'axios'

// lib/api.ts imports lib/keycloak.ts at module scope (getValidToken/logout
// used by its interceptors), which in turn constructs a real Keycloak
// client from keycloak-js. Stubbed here so this file's tests — which only
// exercise the pure error-envelope parsing functions, not the interceptors
// themselves — don't depend on VITE_* env vars being present in whatever
// mode Vitest happens to run in.
vi.mock('../keycloak', () => ({
  getValidToken: vi.fn().mockResolvedValue(null),
  logout: vi.fn(),
  isAuthEnabled: false,
}))

const { getApiErrorMessage, getRetryAfterSeconds, isApiError } = await import('../api')

function makeApiError(status: number, body: unknown): AxiosError {
  const headers = new AxiosHeaders()
  return new AxiosError('Request failed', String(status), undefined, undefined, {
    status,
    statusText: '',
    headers,
    config: { headers },
    data: body,
  })
}

describe('isApiError', () => {
  it('recognizes the { error: {...} } envelope from rate_limit_exceeded_handler / PVHError', () => {
    const err = makeApiError(429, { error: { code: 'RATE_LIMIT_EXCEEDED', message: 'too fast' } })
    expect(isApiError(err)).toBe(true)
  })

  it('rejects a plain network error with no response body', () => {
    const err = new AxiosError('Network Error')
    expect(isApiError(err)).toBe(false)
  })

  it('rejects a non-axios error', () => {
    expect(isApiError(new Error('boom'))).toBe(false)
  })
})

describe('getApiErrorMessage', () => {
  it('extracts the message from the API error envelope', () => {
    const err = makeApiError(403, { error: { code: 'FORBIDDEN', message: "Role 'analyst' not in ('admin',)" } })
    expect(getApiErrorMessage(err)).toBe("Role 'analyst' not in ('admin',)")
  })

  it('appends retry_after_seconds for a 429, matching middleware/rate_limit.py\'s envelope', () => {
    const err = makeApiError(429, {
      error: { code: 'RATE_LIMIT_EXCEEDED', message: 'Rate limit exceeded: 1000 per 1 minute', retry_after_seconds: 42 },
    })
    expect(getApiErrorMessage(err)).toBe('Rate limit exceeded: 1000 per 1 minute — retry in 42s')
  })

  it('falls back to a generic message when there is no response at all (network failure)', () => {
    const err = new AxiosError('Network Error')
    expect(getApiErrorMessage(err)).toBe('Could not reach the API — check your connection.')
  })

  it('falls back to a status-coded message for a non-enveloped error response', () => {
    const err = makeApiError(500, 'plain text error, not our envelope')
    expect(getApiErrorMessage(err)).toBe('Request failed (500)')
  })

  it('handles a plain JS Error (non-axios) gracefully', () => {
    expect(getApiErrorMessage(new Error('local validation failed'))).toBe('local validation failed')
  })
})

describe('getRetryAfterSeconds', () => {
  it('returns the numeric value on a 429', () => {
    const err = makeApiError(429, { error: { code: 'RATE_LIMIT_EXCEEDED', message: 'x', retry_after_seconds: 7 } })
    expect(getRetryAfterSeconds(err)).toBe(7)
  })

  it('returns null for a non-429 error', () => {
    const err = makeApiError(403, { error: { code: 'FORBIDDEN', message: 'x' } })
    expect(getRetryAfterSeconds(err)).toBeNull()
  })
})
