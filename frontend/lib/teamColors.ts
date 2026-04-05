export const TEAM_COLORS: Record<string, string> = {
  'Red Bull Racing': '#3671C6',
  'Red Bull': '#3671C6',
  'McLaren': '#FF8000',
  'Ferrari': '#E8002D',
  'Mercedes': '#00A3E0',
  'Aston Martin': '#229971',
  'Alpine': '#FF87BC',
  'Alpine F1 Team': '#FF87BC',
  'Williams': '#64C4FF',
  'RB': '#6692FF',
  'Racing Bulls': '#6692FF',
  'Visa Cash App RB': '#6692FF',
  'Kick Sauber': '#52E252',
  'Audi': '#C0C0C0',
  'Haas F1 Team': '#B6BABD',
  'Haas': '#B6BABD',
}

export function getTeamColor(team: string): string {
  return TEAM_COLORS[team] ?? '#666666'
}
