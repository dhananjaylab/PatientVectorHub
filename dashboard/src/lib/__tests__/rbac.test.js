import { describe, expect, it } from 'vitest';
import { hasExactRole, hasMinRole, roleLabel, ROLE_HIERARCHY } from '../rbac';
describe('rbac.hasMinRole', () => {
    it('allows a role exactly at the minimum', () => {
        expect(hasMinRole('analyst', 'analyst')).toBe(true);
    });
    it('allows a role above the minimum', () => {
        expect(hasMinRole('admin', 'analyst')).toBe(true);
    });
    it('rejects a role below the minimum', () => {
        expect(hasMinRole('readonly', 'analyst')).toBe(false);
    });
    it('treats an unknown/garbage role as below every real role', () => {
        expect(hasMinRole('not-a-real-role', 'readonly')).toBe(false);
    });
    it('mirrors api-gateway/src/middleware/rbac.py\'s exact hierarchy values', () => {
        expect(ROLE_HIERARCHY).toEqual({ admin: 4, engineer: 3, analyst: 2, auditor: 1, readonly: 0 });
    });
});
describe('rbac.hasExactRole', () => {
    it('matches when the role is in the allow-list', () => {
        expect(hasExactRole('auditor', 'admin', 'auditor')).toBe(true);
    });
    it('rejects a higher-privileged role not explicitly in the allow-list', () => {
        // Matches routers/audit.py's export gate: require_role("admin", "auditor")
        // has NO min-role fallback — engineer/analyst are rejected even though
        // they outrank auditor in the hierarchy.
        expect(hasExactRole('engineer', 'admin', 'auditor')).toBe(false);
    });
});
describe('rbac.roleLabel', () => {
    it('capitalizes a known role', () => {
        expect(roleLabel('engineer')).toBe('Engineer');
    });
    it('falls back to Unknown for a role not in the priority list', () => {
        expect(roleLabel('bogus')).toBe('Unknown');
    });
});
