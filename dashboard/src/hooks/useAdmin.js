/**
 * dashboard/src/hooks/useAdmin.ts
 *
 * New in Phase 9. Types are a direct copy of schemas/admin.py. Two
 * different RBAC floors live in this one file, matching
 * routers/admin.py's own module docstring on why that's intentional
 * (per-route RBAC, not a uniform per-file boundary):
 *   - API keys / users: require_role("admin") — exact match, no
 *     engineer/analyst fallback.
 *   - Namespace health: require_min_role("engineer") — engineers doing
 *     routine ingestion ops need this, per doc 03's Vector Store page
 *     access level.
 * AdminLayout.tsx's route guards reflect this split; the two lower-role
 * pages (namespaces) are NOT nested under the same min="admin" Guard
 * the API-keys/users pages use.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
export const API_KEY_SCOPES = ['ingest:write', 'query:read', 'audit:read', 'admin:write'];
/** Requires admin. Rate limited 20/min. */
export function useApiKeys() {
    return useQuery({
        queryKey: ['admin-api-keys'],
        queryFn: async () => {
            const { data } = await api.get('/admin/api-keys');
            return data.api_keys;
        },
    });
}
/** Requires admin. Rate limited 20/min. */
export function useCreateApiKey() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (payload) => {
            const { data } = await api.post('/admin/api-keys', payload);
            return data;
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-api-keys'] }),
    });
}
/** Requires admin. Rate limited 20/min. 204 on success — 404 if the key
 * doesn't exist (surfaced via getApiErrorMessage in the caller). */
export function useRevokeApiKey() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: async (keyId) => {
            await api.delete(`/admin/api-keys/${keyId}`);
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-api-keys'] }),
    });
}
/** Requires admin. Rate limited 200/min. */
export function useAdminUsers() {
    return useQuery({
        queryKey: ['admin-users'],
        queryFn: async () => {
            const { data } = await api.get('/admin/users');
            return data.users;
        },
    });
}
/** Requires engineer+ (lower floor than the rest of this file — see
 * module docstring). Rate limited 200/min. Polled every 15s so the
 * Vector Store Health page reflects the real current state without a
 * manual refresh, but not so aggressively that it adds meaningful load
 * to Weaviate/Qdrant's health_check() call. */
export function useNamespaceHealth() {
    return useQuery({
        queryKey: ['admin-namespace-health'],
        queryFn: async () => {
            const { data } = await api.get('/admin/vector-store/namespaces');
            return data;
        },
        refetchInterval: 15_000,
    });
}
