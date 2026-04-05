import type { Source } from '@/lib/types'

interface Props {
  source: Source
}

export function SourceChip({ source }: Props) {
  return (
    <span className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] border"
      style={{ background: 'var(--f1-surface-2)', borderColor: 'var(--f1-border)', color: 'var(--f1-muted)' }}>
      <span style={{ color: 'var(--f1-red)' }}>◈</span>
      {source.source}
      {source.content_type ? ` · ${source.content_type}` : ''}
    </span>
  )
}
