'use client'

import { useState, useRef, KeyboardEvent } from 'react'

interface Props {
  onSend: (query: string) => void
  disabled?: boolean
}

export function ChatInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const submit = () => {
    const q = value.trim()
    if (!q || disabled) return
    onSend(q)
    setValue('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const handleInput = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
  }

  return (
    <div className="flex gap-2 items-end p-4 border-t" style={{ borderColor: 'var(--f1-border)', background: '#0d0d0d' }}>
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        disabled={disabled}
        onChange={e => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        aria-label="Chat message"
        placeholder="Ask about F1 history or the current season..."
        className="flex-1 resize-none rounded-lg px-3.5 py-2.5 text-sm outline-none disabled:opacity-50"
        style={{
          background: 'var(--f1-surface-2)',
          border: '1px solid var(--f1-border)',
          color: 'var(--f1-text)',
          fontFamily: 'inherit',
          lineHeight: '1.5',
        }}
        onFocus={e => e.target.style.borderColor = 'var(--f1-red)'}
        onBlur={e => e.target.style.borderColor = 'var(--f1-border)'}
      />
      <button
        onClick={submit}
        disabled={disabled || !value.trim()}
        className="flex-shrink-0 rounded-lg px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
        style={{ background: 'var(--f1-red)' }}
      >
        Send
      </button>
    </div>
  )
}
