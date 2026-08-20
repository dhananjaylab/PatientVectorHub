/**
 * Zustand auth store — holds the authenticated user's identity and role.
 * Populated by App.tsx after Keycloak init. Unchanged in shape since
 * Phase 1; Phase 9 only tightens `role`'s type to the shared Role union
 * (lib/rbac.ts) instead of a bare `string`.
 */
import { create } from 'zustand'
import type { Role } from '../lib/rbac'

interface AuthState {
  userId: string
  email: string
  role: Role
  tenantId: string
  authenticated: boolean
  setUser: (u: Omit<AuthState, 'setUser' | 'reset' | 'authenticated'>) => void
  reset: () => void
}

const initial = {
  userId: '',
  email: '',
  role: 'readonly' as Role,
  tenantId: '',
  authenticated: false,
}

export const useAuthStore = create<AuthState>((set) => ({
  ...initial,
  setUser: (u) => set({ ...u, authenticated: true }),
  reset: () => set(initial),
}))
