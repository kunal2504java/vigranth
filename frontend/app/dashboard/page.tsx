"use client"

import { useMemo } from "react"
import { Search, RefreshCw } from "lucide-react"
import { useStore } from "@/lib/store"
import { PriorityFeed } from "@/components/app/priority-feed"
import { ScrollArea } from "@/components/ui/scroll-area"

const FILTER_LABELS: Record<string, string> = {
  all: "All Messages",
  urgent: "Urgent",
  action_needed: "Action Needed",
  fyi: "FYI",
  snoozed: "Snoozed",
  gmail: "Gmail",
  slack: "Slack",
  discord: "Discord",
  telegram: "Telegram",
}

export default function DashboardPage() {
  const { activeFilter, searchQuery, setSearchQuery, lastSynced, triggerSync } =
    useStore()

  const title = FILTER_LABELS[activeFilter] ?? "All Messages"

  const syncLabel = useMemo(() => {
    if (!lastSynced) return "Never synced"
    const diff = Date.now() - lastSynced.getTime()
    const min = Math.floor(diff / 60000)
    if (min < 1) return "Just synced"
    if (min < 60) return `${min} min ago`
    return `${Math.floor(min / 60)}h ago`
  }, [lastSynced])

  return (
    <div className="flex flex-col h-screen">
      {/* ── Top bar ──────────────────────────────────── */}
      <div className="px-6 py-4 border-b-2 border-foreground shrink-0">
        <div className="flex items-center justify-between gap-4">
          {/* Title + sync */}
          <div className="flex items-center gap-4">
            <h1 className="text-sm font-mono font-bold tracking-wider uppercase">
              {title}
            </h1>
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground">
              <span>Last synced: {syncLabel}</span>
              <button
                onClick={triggerSync}
                className="p-0.5 hover:text-foreground transition-colors"
                title="Refresh"
              >
                <RefreshCw size={10} />
              </button>
            </div>
          </div>

          {/* Search */}
          <div className="relative w-64">
            <Search
              size={13}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <input
              id="search-input"
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search messages..."
              className="w-full pl-8 pr-3 py-2 border-2 border-foreground/10 bg-transparent text-xs font-mono focus:outline-none focus:border-foreground/30 placeholder:text-muted-foreground/40 transition-colors"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-mono text-muted-foreground hover:text-foreground"
              >
                Clear
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Feed ─────────────────────────────────────── */}
      <ScrollArea className="flex-1">
        <div className="p-6">
          <PriorityFeed />
        </div>
      </ScrollArea>
    </div>
  )
}
