/**
 * dashboard/src/pages/admin/AdminLayout.tsx
 *
 * New in Phase 9. Sub-nav tabs are individually role-gated rather than
 * the whole /admin/* subtree sharing one guard — matches
 * routers/admin.py's own module docstring precedent: "this file is an
 * organizational grouping (admin-surface routes), not a uniform-
 * permission boundary." App.tsx's top-level route guard for /admin/*
 * only requires engineer+ (the lowest floor of any page under this
 * layout, namespace health); AdminApiKeysPage / AdminUsersPage each
 * carry their own stricter admin-only Guard internally.
 */
import { NavLink, Outlet } from 'react-router'

export function AdminLayout() {
  return (
    <div className="admin-layout">
      <h1>Admin</h1>
      <nav className="sub-tabs">
        <NavLink to="/admin/api-keys" className={({ isActive }) => (isActive ? 'sub-tab active' : 'sub-tab')}>
          API Keys
        </NavLink>
        <NavLink to="/admin/users" className={({ isActive }) => (isActive ? 'sub-tab active' : 'sub-tab')}>
          Users
        </NavLink>
        <NavLink to="/admin/namespaces" className={({ isActive }) => (isActive ? 'sub-tab active' : 'sub-tab')}>
          Vector Store
        </NavLink>
      </nav>
      <div className="admin-content">
        <Outlet />
      </div>
    </div>
  )
}
