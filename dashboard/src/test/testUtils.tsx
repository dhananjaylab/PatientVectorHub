/**
 * dashboard/src/test/testUtils.tsx
 *
 * Shared `renderWithProviders` used across component/hook tests.
 * `retry: false` on the QueryClient is deliberate, not a default we
 * happened to leave on — TanStack Query's default retry behavior
 * (3 attempts with exponential backoff) would make any test that
 * exercises an error path take several real seconds and produce the
 * exact "update not wrapped in act()" warnings React 19 + RTL 16 flag
 * when a state update lands after the test function has already
 * returned. See docs/PHASE_9_IMPLEMENTATION_PLAN.md §6 for the
 * act()-warning research this setup is based on.
 */
import type { ReactElement, ReactNode } from 'react'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

interface WrapperOptions {
  route?: string
  queryClient?: QueryClient
}

export function renderWithProviders(ui: ReactElement, { route = '/', queryClient = createTestQueryClient() }: WrapperOptions = {}) {
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
      </QueryClientProvider>
    )
  }
  return { ...render(ui, { wrapper: Wrapper }), queryClient }
}
