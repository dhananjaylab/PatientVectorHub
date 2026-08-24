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
import userEvent from '@testing-library/user-event'
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

describe('AuditLogTable phi_reveal logging (Phase 10 / ADR-017)', () => {
  const singleLogPage = {
    logs: [
      {
        id: 'log-1',
        user_id: 'user-abc12345',
        action: 'document_query',
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
  }

  it('POSTs /audit/phi-reveal with the row id and patient_id on hover', async () => {
    setRole('auditor')
    vi.mocked(api.get).mockResolvedValue({ data: singleLogPage })
    vi.mocked(api.post).mockResolvedValue({ data: undefined })
    const user = userEvent.setup()
    renderWithProviders(<AuditLogTable />)

    const cell = await screen.findByText('patient-xyz')
    await user.hover(cell)

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/audit/phi-reveal', {
        audit_log_id: 'log-1',
        patient_id: 'patient-xyz',
      }),
    )
  })

  it('fires again on a second hover of the same row — each reveal is its own audit event', async () => {
    setRole('auditor')
    vi.mocked(api.get).mockResolvedValue({ data: singleLogPage })
    vi.mocked(api.post).mockResolvedValue({ data: undefined })
    const user = userEvent.setup()
    renderWithProviders(<AuditLogTable />)

    const cell = await screen.findByText('patient-xyz')
    await user.hover(cell)
    await user.unhover(cell)
    await user.hover(cell)

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2))
  })

  it('does not call phi-reveal for a row with no patient_id', async () => {
    setRole('auditor')
    vi.mocked(api.get).mockResolvedValue({
      data: {
        logs: [{ ...singleLogPage.logs[0], patient_id: null }],
        total: 1,
        limit: 50,
        offset: 0,
      },
    })
    const user = userEvent.setup()
    renderWithProviders(<AuditLogTable />)

    const cell = await screen.findByText('—')
    await user.hover(cell)

    expect(api.post).not.toHaveBeenCalled()
  })

  it('a phi-reveal logging failure does not affect the already-visible cell content', async () => {
    setRole('auditor')
    vi.mocked(api.get).mockResolvedValue({ data: singleLogPage })
    vi.mocked(api.post).mockRejectedValue(new Error('network error'))
    const user = userEvent.setup()
    renderWithProviders(<AuditLogTable />)

    const cell = await screen.findByText('patient-xyz')
    await user.hover(cell)

    await waitFor(() => expect(api.post).toHaveBeenCalled())
    // Still rendered, unaffected by the mutation's own failure -- the
    // reveal is a fire-and-forget side effect, not a gate on display.
    expect(screen.getByText('patient-xyz')).toBeInTheDocument()
  })
})
