import { ChatPanel } from '@/components/chat/ChatPanel'
import { StandingsPanel } from '@/components/standings/StandingsPanel'

export function SplitLayout() {
  return (
    <div className="flex flex-1 overflow-hidden">
      <ChatPanel />
      {/* Standings panel hidden on mobile, visible on md+ */}
      <div className="hidden md:flex">
        <StandingsPanel />
      </div>
    </div>
  )
}
