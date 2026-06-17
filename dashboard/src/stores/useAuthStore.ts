/**
 * Zustand auth store — holds the authenticated user's identity and role.
 * Populated by App.tsx after Keycloak init.
 */
import { create } from 'zustand'

interface AuthState {
  userId:   string
  email:    string
  role:     string
  tenantId: string
  setUser:  (u: Omit<AuthState, 'setUser' | 'reset'>) => void
  reset:    () => void
}

export const useAuthStore = create<AuthState>(set => ({
  userId:   '',
  email:    '',
  role:     'readonly',
  tenantId: '',
  setUser:  u  => set(u),
  reset:    () => set({ userId: '', email: '', role: 'readonly', tenantId: '' }),
}))
