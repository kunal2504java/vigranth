"use client"

import { useMemo, useState } from "react"
import { AnimatePresence } from "framer-motion"
import { ChevronUp, ChevronDown } from "lucide-react"
import { useStore } from "@/lib/store"
import { MessageCard } from "./message-card"
import { EmptyState } from "./empty-state"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import type { Message } from "@/lib/types"

export function PriorityFeed() {
  const { messages, activeFilter, searchQuery, selectedMessageId } = useStore()

  const filtered = useMemo(() => {
    let result = messages.filter((m) => !m.isDone)

    // Filter
    if (activeFilter === "snoozed") {
      result = result.filter((m) => m.snoozedUntil)
    } else {
      result = result.filter((m) => !m.snoozedUntil)
      switch (activeFilter) {
        case "urgent":
          result = result.filter((m) => m.priority === "urgent")
          break
        case "action_needed":
          result = result.filter((m) => m.priority === "action_needed")
          break
        case "fyi":
          result = result.filter(
            (m) => m.priority === "fyi" || m.priority === "noise"
          )
          break
        case "gmail":
        case "slack":
        case "discord":
        case "telegram":
          result = result.filter((m) => m.platform === activeFilter)
          break
      }
    }

    // Search
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      result = result.filter(
        (m) =>
          m.sender.name.toLowerCase().includes(q) ||
          m.preview.toLowerCase().includes(q) ||
          (m.subject?.toLowerCase().includes(q) ?? false)
      )
    }

    result.sort((a, b) => b.priorityScore - a.priorityScore)
    return result
  }, [messages, activeFilter, searchQuery])

  // Single-filter views (not "all")
  if (activeFilter !== "all") {
    if (filtered.length === 0) {
      return <FilterEmptyState filter={activeFilter} query={searchQuery} />
    }
    return (
      <div className="space-y-2">
        <AnimatePresence mode="popLayout">
          {filtered.map((m) => (
            <MessageCard
              key={m.id}
              message={m}
              isSelected={m.id === selectedMessageId}
            />
          ))}
        </AnimatePresence>
      </div>
    )
  }

  // "All" — group by priority
  const urgent = filtered.filter((m) => m.priority === "urgent")
  const action = filtered.filter((m) => m.priority === "action_needed")
  const fyi = filtered.filter(
    (m) => m.priority === "fyi" || m.priority === "noise"
  )

  if (filtered.length === 0) {
    if (searchQuery) {
      return (
        <EmptyState
          title="No results"
          description={`No messages found for "${searchQuery}"`}
        />
      )
    }
    return (
      <EmptyState
        title="Inbox zero"
        description="Connecting to your platforms... first sync in progress"
      />
    )
  }

  return (
    <div className="space-y-4">
      <PrioritySection
        label="Urgent"
        icon="\u{1F534}"
        messages={urgent}
        selectedId={selectedMessageId}
        defaultOpen
      />
      <PrioritySection
        label="Action Needed"
        icon="\u{1F7E1}"
        messages={action}
        selectedId={selectedMessageId}
        defaultOpen
      />
      <PrioritySection
        label="FYI / Later"
        icon="\u{1F4AC}"
        messages={fyi}
        selectedId={selectedMessageId}
        defaultOpen={false}
      />
    </div>
  )
}

/* ── Collapsible priority section ─────────────────────── */

function PrioritySection({
  label,
  icon,
  messages,
  selectedId,
  defaultOpen,
}: {
  label: string
  icon: string
  messages: Message[]
  selectedId: string | null
  defaultOpen: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)

  if (messages.length === 0) return null

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button className="w-full flex items-center gap-2 px-3 py-2.5 border-2 border-foreground/10 bg-muted/30 hover:bg-muted/50 transition-colors">
          <span className="text-sm">{icon}</span>
          <span className="text-[11px] font-mono font-bold tracking-wider uppercase">
            {label}
          </span>
          <span className="text-[10px] font-mono text-muted-foreground">
            ({messages.length})
          </span>
          <span className="ml-auto text-muted-foreground">
            {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="space-y-2 mt-2">
          <AnimatePresence mode="popLayout">
            {messages.map((m) => (
              <MessageCard
                key={m.id}
                message={m}
                isSelected={m.id === selectedId}
              />
            ))}
          </AnimatePresence>
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

/* ── Empty state by filter ────────────────────────────── */

function FilterEmptyState({
  filter,
  query,
}: {
  filter: string
  query: string
}) {
  if (query) {
    return (
      <EmptyState
        title="No results"
        description={`No messages found for "${query}"`}
      />
    )
  }

  const map: Record<string, { title: string; description: string }> = {
    urgent: {
      title: "All caught up",
      description: "You're all caught up on urgent items",
    },
    action_needed: {
      title: "No actions pending",
      description: "Nothing needs your attention right now",
    },
    fyi: {
      title: "No FYI messages",
      description: "No informational messages at the moment",
    },
    snoozed: {
      title: "Nothing snoozed",
      description: "Nothing snoozed. You're on top of things.",
    },
  }

  const state = map[filter] ?? {
    title: "No messages",
    description: "No messages from this platform yet",
  }

  return <EmptyState title={state.title} description={state.description} />
}
