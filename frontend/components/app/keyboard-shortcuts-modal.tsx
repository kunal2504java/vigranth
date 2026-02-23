"use client"

import { useEffect, useState, useCallback } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useStore } from "@/lib/store"

const SHORTCUTS = [
  { keys: ["J"], description: "Move down in feed" },
  { keys: ["K"], description: "Move up in feed" },
  { keys: ["Enter"], description: "Open thread panel" },
  { keys: ["R"], description: "Draft AI reply" },
  { keys: ["S"], description: "Snooze selected message" },
  { keys: ["D"], description: "Mark selected as done" },
  { keys: ["Escape"], description: "Close thread panel" },
  { keys: ["/"], description: "Focus search bar" },
  { keys: ["?"], description: "Show this dialog" },
]

export function KeyboardShortcutsModal() {
  const [open, setOpen] = useState(false)
  const { messages, selectedMessageId, selectMessage, markDone, snoozeMessage } =
    useStore()

  const toggle = useCallback(() => setOpen((o) => !o), [])

  // Listen for custom event from sidebar
  useEffect(() => {
    document.addEventListener("toggle-shortcuts", toggle)
    return () => document.removeEventListener("toggle-shortcuts", toggle)
  }, [toggle])

  // Global keyboard shortcuts
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      // Ignore if typing in an input/textarea
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return

      switch (e.key) {
        case "?":
          e.preventDefault()
          toggle()
          break

        case "Escape":
          if (open) {
            setOpen(false)
          } else {
            selectMessage(null)
          }
          break

        case "j":
        case "J": {
          e.preventDefault()
          const active = messages.filter((m) => !m.isDone && !m.snoozedUntil)
          active.sort((a, b) => b.priorityScore - a.priorityScore)
          if (active.length === 0) break
          const currentIdx = active.findIndex(
            (m) => m.id === selectedMessageId
          )
          const nextIdx =
            currentIdx < 0 ? 0 : Math.min(currentIdx + 1, active.length - 1)
          selectMessage(active[nextIdx].id)
          break
        }

        case "k":
        case "K": {
          e.preventDefault()
          const active = messages.filter((m) => !m.isDone && !m.snoozedUntil)
          active.sort((a, b) => b.priorityScore - a.priorityScore)
          if (active.length === 0) break
          const currentIdx = active.findIndex(
            (m) => m.id === selectedMessageId
          )
          const prevIdx = currentIdx <= 0 ? 0 : currentIdx - 1
          selectMessage(active[prevIdx].id)
          break
        }

        case "Enter":
          // Already handled by selectMessage in the card click
          break

        case "d":
        case "D":
          if (selectedMessageId) {
            e.preventDefault()
            markDone(selectedMessageId)
          }
          break

        case "s":
        case "S":
          if (selectedMessageId) {
            e.preventDefault()
            // Snooze for 2 hours by default
            snoozeMessage(
              selectedMessageId,
              new Date(Date.now() + 2 * 60 * 60 * 1000)
            )
          }
          break

        case "/":
          e.preventDefault()
          document.getElementById("search-input")?.focus()
          break
      }
    }

    document.addEventListener("keydown", handleKey)
    return () => document.removeEventListener("keydown", handleKey)
  }, [
    open,
    toggle,
    messages,
    selectedMessageId,
    selectMessage,
    markDone,
    snoozeMessage,
  ])

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="border-2 border-foreground font-mono max-w-md">
        <DialogHeader>
          <DialogTitle className="text-sm font-mono font-bold tracking-wider uppercase">
            Keyboard Shortcuts
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-1 mt-2">
          {SHORTCUTS.map((s) => (
            <div
              key={s.keys.join("+")}
              className="flex items-center justify-between py-2 border-b border-border last:border-0"
            >
              <span className="text-xs text-muted-foreground">
                {s.description}
              </span>
              <div className="flex items-center gap-1">
                {s.keys.map((key) => (
                  <kbd
                    key={key}
                    className="inline-flex items-center justify-center min-w-[24px] px-1.5 py-0.5 border-2 border-foreground bg-muted text-[10px] font-mono font-bold uppercase"
                  >
                    {key}
                  </kbd>
                ))}
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
