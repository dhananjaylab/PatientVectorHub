/**
 * dashboard/src/components/common/StatusBadge.tsx
 *
 * Shared status pill — doc 04's UI/UX brief specifies dot + label with
 * a pulsing animation for live states (Running). Reused by
 * JobProgressCard (ingestion status) and AdminApiKeysPage (revoked/active).
 */
const COLORS: Record<string, string> = {
  queued: 'var(--color-warning)',
  running: 'var(--color-primary)',
  completed: 'var(--color-success)',
  completed_with_errors: 'var(--color-warning)',
  failed: 'var(--color-danger)',
  cancelled: 'var(--color-text-tertiary, #64748B)',
  active: 'var(--color-success)',
  revoked: 'var(--color-danger)',
}

const PULSE = new Set(['running', 'queued'])

interface Props {
  status: string
  label?: string
}

export function StatusBadge({ status, label }: Props) {
  const color = COLORS[status] ?? 'var(--color-text-secondary, #94A3B8)'
  return (
    <span className="status-badge" style={{ color }}>
      <span className={PULSE.has(status) ? 'status-dot status-dot-pulse' : 'status-dot'} style={{ background: color }} />
      {(label ?? status).replace(/_/g, ' ').toUpperCase()}
    </span>
  )
}
