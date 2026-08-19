/**
 * Zustand auth store — holds the authenticated user's identity and role.
 * Populated by App.tsx after Keycloak init. Unchanged in shape since
 * Phase 1; Phase 9 only tightens `role`'s type to the shared Role union
 * (lib/rbac.ts) instead of a bare `string`.
 */
import { create } from 'zustand';
const initial = {
    userId: '',
    email: '',
    role: 'readonly',
    tenantId: '',
    authenticated: false,
};
export const useAuthStore = create((set) => ({
    ...initial,
    setUser: (u) => set({ ...u, authenticated: true }),
    reset: () => set(initial),
}));
