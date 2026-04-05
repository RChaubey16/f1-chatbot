interface Props {
  active: 'drivers' | 'constructors'
  onChange: (tab: 'drivers' | 'constructors') => void
}

export function StandingsTabs({ active, onChange }: Props) {
  const tabs = [
    { key: 'drivers', label: 'Drivers' },
    { key: 'constructors', label: 'Constructors' },
  ] as const

  return (
    <div className="flex border-b" style={{ borderColor: 'var(--f1-border)' }}>
      {tabs.map(tab => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className="flex-1 py-2 text-xs font-medium transition-colors border-b-2"
          style={{
            color: active === tab.key ? 'var(--f1-red)' : 'var(--f1-muted)',
            borderBottomColor: active === tab.key ? 'var(--f1-red)' : 'transparent',
            background: 'transparent',
          }}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}
