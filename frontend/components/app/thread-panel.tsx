"use client"

import { useMemo } from "react"
import { motion } from "framer-motion"
import { X, AlertTriangle, Sparkles } from "lucide-react"
import { useStore } from "@/lib/store"
import { PlatformIcon, getPlatformName } from "./platform-icon"
import { ReplyComposer } from "./reply-composer"
import { ScrollArea } from "@/components/ui/scroll-area"
import { MOCK_THREADS } from "@/lib/mock-data"
import type { Message } from "@/lib/types"

interface ThreadPanelProps {
  message: Message
  onClose: () => void
}

export function ThreadPanel({ message, onClose }: ThreadPanelProps) {
  const { markDone } = useStore()

  const thread = useMemo(
    () => MOCK_THREADS[message.threadId],
    [message.threadId]
  )

  const showSummary = thread && thread.summary && thread.messages.length > 4
  const showSentimentWarning =
    message.sentiment === "tense" || message.sentiment === "distressed"

  function handleSend(_content: string) {
    markDone(message.id)
  }

  return (
    <motion.div
      initial={{ x: 30, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 30, opacity: 0 }}
      transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
      className="w-[420px] border-l-2 border-foreground bg-background flex flex-col h-screen shrink-0"
    >
      {/* ── Header ───────────────────────────────────── */}
      <div className="px-4 py-4 border-b-2 border-foreground">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            {/* Sender avatar */}
            <div className="w-9 h-9 bg-muted border-2 border-foreground flex items-center justify-center shrink-0">
              <span className="text-xs font-mono font-bold">
                {message.sender.name
                  .split(" ")
                  .map((n) => n[0])
                  .join("")}
              </span>
            </div>
            <div className="min-w-0">
              <h2 className="text-sm font-mono font-bold truncate">
                {message.sender.name}
              </h2>
              <div className="flex items-center gap-2 mt-0.5">
                <PlatformIcon platform={message.platform} size="sm" />
                <span className="text-[10px] font-mono text-muted-foreground">
                  via {getPlatformName(message.platform)}
                </span>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 hover:bg-muted transition-colors shrink-0"
          >
            <X size={16} />
          </button>
        </div>

        {/* Relationship tag */}
        <div className="flex items-center gap-2 mt-3">
          <span className="text-[10px] font-mono tracking-wider text-muted-foreground border border-border px-2 py-0.5">
            {message.sender.relationship}
          </span>
          <span className="text-[10px] font-mono text-muted-foreground">
            {message.sender.conversationCount} previous conversations
          </span>
        </div>
      </div>

      {/* ── Content area ─────────────────────────────── */}
      <ScrollArea className="flex-1">
        <div className="p-4 space-y-4">
          {/* AI Summary banner */}
          {showSummary && thread.summary && (
            <div className="border-2 border-[#ea580c]/30 bg-orange-50/50 dark:bg-orange-950/10 p-3">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles size={12} className="text-[#ea580c]" />
                <span className="text-[10px] font-mono font-bold tracking-wider uppercase text-[#ea580c]">
                  AI Summary
                </span>
              </div>
              <ul className="space-y-1">
                {thread.summary.points.map((point, i) => (
                  <li
                    key={i}
                    className="text-[11px] font-mono text-foreground/80 flex items-start gap-2"
                  >
                    <span className="text-muted-foreground shrink-0">
                      &bull;
                    </span>
                    {point}
                  </li>
                ))}
              </ul>
              <p className="text-[10px] font-mono text-muted-foreground mt-2">
                Tone: {thread.summary.tone}
              </p>
            </div>
          )}

          {/* Sentiment warning */}
          {showSentimentWarning && message.sentimentAdvice && (
            <div className="border-2 border-amber-500/30 bg-amber-50/50 dark:bg-amber-950/10 p-3">
              <div className="flex items-center gap-2 mb-1.5">
                <AlertTriangle size={12} className="text-amber-500" />
                <span className="text-[10px] font-mono font-bold tracking-wider uppercase text-amber-600 dark:text-amber-400">
                  Tense Tone Detected
                </span>
              </div>
              <p className="text-[11px] font-mono text-foreground/80">
                {message.sentimentAdvice}
              </p>
            </div>
          )}

          {/* Thread messages */}
          {thread ? (
            <div className="space-y-3">
              {thread.messages.map((tm) => (
                <div
                  key={tm.id}
                  className={`flex ${tm.isMe ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] ${
                      tm.isMe
                        ? "bg-foreground text-background"
                        : "bg-muted border border-foreground/10"
                    } p-3`}
                  >
                    <div className="flex items-center justify-between gap-4 mb-1.5">
                      <span className="text-[10px] font-mono font-bold tracking-wider">
                        {tm.isMe ? "You" : tm.senderName}
                      </span>
                      <span
                        className={`text-[9px] font-mono ${
                          tm.isMe
                            ? "text-background/50"
                            : "text-muted-foreground"
                        }`}
                      >
                        {formatTime(tm.sentAt)}
                      </span>
                    </div>
                    <p
                      className={`text-[11px] font-mono leading-relaxed whitespace-pre-wrap ${
                        tm.isMe ? "text-background/90" : "text-foreground/80"
                      }`}
                    >
                      {tm.content}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            /* Single message (no thread) */
            <div className="bg-muted border border-foreground/10 p-3">
              <div className="flex items-center justify-between gap-4 mb-1.5">
                <span className="text-[10px] font-mono font-bold tracking-wider">
                  {message.sender.name}
                </span>
                <span className="text-[9px] font-mono text-muted-foreground">
                  {formatTime(message.receivedAt)}
                </span>
              </div>
              <p className="text-[11px] font-mono leading-relaxed whitespace-pre-wrap text-foreground/80">
                {message.content}
              </p>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* ── Reply composer ────────────────────────────── */}
      <ReplyComposer platform={message.platform} onSend={handleSend} />
    </motion.div>
  )
}

function formatTime(date: Date): string {
  const diff = Date.now() - date.getTime()
  const min = Math.floor(diff / 60000)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  const days = Math.floor(hr / 24)
  if (days < 7) return `${days}d ago`
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" })
}
