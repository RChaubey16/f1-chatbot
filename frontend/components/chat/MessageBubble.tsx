import type { Message } from '@/lib/types'
import { SourceChip } from './SourceChip'

interface Props {
  message: Message
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div
        className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
        style={
          isUser
            ? { background: 'var(--f1-surface-2)', border: '1px solid var(--f1-border)', color: 'var(--f1-muted)' }
            : { background: 'var(--f1-red)', color: '#fff' }
        }
      >
        {isUser ? 'U' : 'F1'}
      </div>

      {/* Content */}
      <div className={`flex flex-col gap-2 max-w-[75%] ${isUser ? 'items-end' : 'items-start'}`}>
        {/* Intent + latency (AI only) */}
        {!isUser && message.intent && (
          <div className="flex items-center gap-2 text-[11px]" style={{ color: 'var(--f1-muted)' }}>
            <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide"
              style={{ background: 'var(--f1-surface-2)', border: '1px solid var(--f1-border)', color: 'var(--f1-red)' }}>
              {message.intent}
            </span>
            {message.latency_ms != null && <span>· {Math.round(message.latency_ms)}ms</span>}
          </div>
        )}

        {/* Bubble */}
        <div
          className="rounded-xl px-4 py-3 text-sm leading-relaxed"
          style={
            isUser
              ? { background: 'var(--f1-surface-2)', border: '1px solid var(--f1-border)', borderRadius: '12px 2px 12px 12px' }
              : { background: '#160000', border: '1px solid #2a0000', borderRadius: '2px 12px 12px 12px' }
          }
        >
          {message.streaming && !message.content ? (
            <div className="streaming-dots flex gap-1 items-center py-1">
              {[0, 1, 2].map(i => (
                <span
                  key={i}
                  className="w-1.5 h-1.5 rounded-full"
                  style={{
                    background: 'var(--f1-red)',
                    animation: `bounce 1.2s ${i * 0.2}s infinite`,
                  }}
                />
              ))}
            </div>
          ) : (
            message.content
          )}
        </div>

        {/* Sources */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {message.sources.map((s, i) => (
              <SourceChip key={i} source={s} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
