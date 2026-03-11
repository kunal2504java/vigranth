"use client"

import { useMemo } from "react"
import { AnimatePresence } from "framer-motion"
import { Loader2 } from "lucide-react"
import { useStore } from "@/lib/store"
import { useAuthGuard } from "@/hooks/use-auth-guard"
import { Sidebar } from "@/components/app/sidebar"
import { ThreadPanel } from "@/components/app/thread-panel"
import { KeyboardShortcutsModal } from "@/components/app/keyboard-shortcuts-modal"

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { ready } = useAuthGuard()
  const { messages, selectedMessageId, selectMessage } = useStore()

  const selectedMessage = useMemo(
    () => messages.find((m) => m.id === selectedMessageId) ?? null,
    [messages, selectedMessageId]
  )

  if (!ready) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Loader2 size={24} className="animate-spin text-muted-foreground" />
      </div>
    )
  }

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
