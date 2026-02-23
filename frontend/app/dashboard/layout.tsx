"use client"

import { useMemo } from "react"
import { AnimatePresence } from "framer-motion"
import { useStore } from "@/lib/store"
import { Sidebar } from "@/components/app/sidebar"
import { ThreadPanel } from "@/components/app/thread-panel"
import { KeyboardShortcutsModal } from "@/components/app/keyboard-shortcuts-modal"

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { messages, selectedMessageId, selectMessage } = useStore()

  const selectedMessage = useMemo(
    () => messages.find((m) => m.id === selectedMessageId) ?? null,
    [messages, selectedMessageId]
  )

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Left sidebar */}
      <Sidebar />

      {/* Main content */}
      <div className="flex-1 overflow-hidden">{children}</div>

      {/* Right thread panel */}
      <AnimatePresence>
        {selectedMessage && (
          <ThreadPanel
            key={selectedMessage.id}
            message={selectedMessage}
            onClose={() => selectMessage(null)}
          />
        )}
      </AnimatePresence>

      {/* Global modals */}
      <KeyboardShortcutsModal />
    </div>
  )
}
