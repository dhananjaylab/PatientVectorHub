/**
 * dashboard/src/components/__tests__/AuditLogTable.test.tsx
 *
 * Focused on the two RBAC-driven rendering decisions documented in
 * AuditLogTable.tsx's own docstring: the user_id filter and the Export
 * buttons only render for admin/auditor, not analyst/engineer/readonly
 * — because showing them to anyone else would either silently do
 * nothing (user_id filter — routers/audit.py force-overrides it) or
 * 403 on click (export — require_role("admin","auditor") has no
 * min-role fallback).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../../test/testUtils'
import { api } from '../../lib/api'
import { useAuthStore } from '../../stores/useAuthStore'
import { AuditLogTable } from '../audit/AuditLogTable'
import type { Role } from '../../lib/rbac'

vi.mock('../../lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

function setRole(role: Role) {
  useAuthStore.setState({ role, userId: 'u-1', email: 'u@x.test', tenantId: 't-1', authenticated: true })
}

afterEach(() => {
  useAuthStore.getState().reset()
})

const emptyPage = { logs: [], total: 0, limit: 50, offset: 0 }

describe('AuditLogTable RBAC-gated controls', () => {
  it('hides the user_id filter and Export buttons for an analyst', async () => {
    setRole('analyst')
    vi.mocked(api.get).mockResolvedValue({ data: emptyPage })
    renderWithProviders(<AuditLogTable />)
    await waitFor(() => expect(api.get).toHaveBeenCalled())

    expect(screen.queryByPlaceholderText('Filter by user_id')).not.toBeInTheDocument()
    expect(screen.queryByText('Export CSV')).not.toBeInTheDocument()
    expect(screen.queryByText('Export JSON')).not.toBeInTheDocument()
    // patient_id filter IS still available to every role that can see this page at all
    expect(screen.getByPlaceholderText('Filter by patient_id')).toBeInTheDocument()
  })

  it('shows the user_id filter and Export buttons for an auditor', async () => {
    setRole('auditor')
    vi.mocked(api.get).mockResolvedValue({ data: emptyPage })
    renderWithProviders(<AuditLogTable />)
    await waitFor(() => expect(api.get).toHaveBeenCalled())

    expect(screen.getByPlaceholderText('Filter by user_id')).toBeInTheDocument()
    expect(screen.getByText('Export CSV')).toBeInTheDocument()
    expect(screen.getByText('Export JSON')).toBeInTheDocument()
  })

  it('shows the user_id filter and Export buttons for an admin', async () => {
    setRole('admin')
    vi.mocked(api.get).mockResolvedValue({ data: emptyPage })
    renderWithProviders(<AuditLogTable />)
    await waitFor(() => expect(api.get).toHaveBeenCalled())

    expect(screen.getByPlaceholderText('Filter by user_id')).toBeInTheDocument()
    expect(screen.getByText('Export CSV')).toBeInTheDocument()
  })
})

describe('AuditLogTable rendering', () => {
  it('blurs patient_id via the .phi-cell class and shows action/status columns', async () => {
    setRole('admin')
    vi.mocked(api.get).mockResolvedValue({
      data: {
        logs: [
          {
            id: 'log-1',
            user_id: 'user-abc12345',
            action: 'phi_reveal',
            patient_id: 'patient-xyz',
            ip_address: '10.0.0.1',
            request_id: 'req-1',
            status_code: 200,
            created_at: '2026-08-01T12:00:00Z',
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      },
    })
    renderWithProviders(<AuditLogTable />)

    await waitFor(() => expect(screen.getByText('patient-xyz')).toBeInTheDocument())
    expect(screen.getByText('patient-xyz')).toHaveClass('phi-cell')
    expect(screen.getByText('phi_reveal', { selector: '.action-pill' })).toBeInTheDocument()
    expect(screen.getByText('200')).toHaveClass('status-ok')
  })

  it('shows an empty-state row when there are no matching logs', async () => {
    setRole('admin')
    vi.mocked(api.get).mockResolvedValue({ data: emptyPage })
    renderWithProviders(<AuditLogTable />)
    await waitFor(() => expect(screen.getByText(/No audit log entries match/)).toBeInTheDocument())
  })
})
