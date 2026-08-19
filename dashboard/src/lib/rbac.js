export const ROLE_HIERARCHY = {
    admin: 4,
    engineer: 3,
    analyst: 2,
    auditor: 1,
    readonly: 0,
};
export const ROLE_PRIORITY = ['admin', 'engineer', 'analyst', 'auditor', 'readonly'];
export function hasMinRole(role, min) {
    const level = ROLE_HIERARCHY[role] ?? -1;
    return level >= ROLE_HIERARCHY[min];
}
export function hasExactRole(role, ...allowed) {
    return allowed.includes(role);
}
/** Human-readable label for role pills in the top bar / admin tables. */
export function roleLabel(role) {
    const known = ROLE_PRIORITY;
    if (!known.includes(role))
        return 'Unknown';
    return role.charAt(0).toUpperCase() + role.slice(1);
}
