import { getTeamColor } from '@/lib/teamColors'

interface Props {
  position: number
  name: string   // driver full name or constructor name
  team?: string  // only for driver rows
  points: number
}

export function StandingsRow({ position, name, team, points }: Props) {
  const teamName = team ?? name
  const color = getTeamColor(teamName)
  const isTop3 = position <= 3

  return (
    <div className="flex items-center gap-2.5 px-5 py-2 border-b hover:bg-white/5 transition-colors"
      style={{ borderColor: 'var(--f1-border)' }}>
      <span className="w-5 text-center text-xs font-bold flex-shrink-0"
        style={{ color: isTop3 ? 'var(--f1-red)' : 'var(--f1-muted)' }}>
        {position}
      </span>
      <div className="w-0.5 h-7 rounded flex-shrink-0" style={{ background: color }} />
      <div className="flex-1 min-w-0">
        <div className="text-[13px] font-semibold truncate" style={{ color: 'var(--f1-text)' }}>
          {team
            ? `${name.split(' ').slice(-1)[0]}, ${name.split(' ')[0][0]}.`
            : name}
        </div>
        {team && (
          <div className="text-[11px] truncate" style={{ color: 'var(--f1-muted)' }}>{team}</div>
        )}
      </div>
      <span className="text-[13px] font-bold flex-shrink-0" style={{ color: '#aaa' }}>
        {Number.isInteger(points) ? points : points.toFixed(1)}
      </span>
    </div>
  )
}
