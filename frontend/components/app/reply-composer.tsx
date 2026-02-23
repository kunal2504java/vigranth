"use client"

import { useState, useEffect, useRef } from "react"
import { Sparkles, Send } from "lucide-react"
import { toast } from "sonner"
import { getPlatformName } from "./platform-icon"
import type { Platform } from "@/lib/types"

interface ReplyComposerProps {
  platform: Platform
  onSend: (content: string) => void
}

const TONE_MAP: Record<Platform, string> = {
  gmail: "Professional",
  slack: "Casual",
  discord: "Friendly",
  telegram: "Brief",
  whatsapp: "Conversational",
  outlook: "Formal",
}

const MOCK_DRAFTS = [
  "Hi Sarah,\n\nThank you for following up. I'm working on finalizing the Q3 numbers with the finance team now.\n\nYou'll have the complete deck with revenue figures, burn rate, and growth projections by EOD Wednesday \u2014 giving us a buffer before Thursday's deadline.\n\nI'll also include the CAC and LTV metrics the board requested.\n\nBest regards",
  "Thanks for the heads up. Looking into this right now.\n\nChecking the 2:30 PM deployment logs. Will update the team in the next 10 minutes with findings and whether we need a rollback.",
  "Hi Elena,\n\nThank you for flagging this \u2014 you're absolutely right. Those terms should reflect what we agreed on our last call.\n\nI'm looping in Sam from legal now to correct clause 4.2 to NET-30 and remove the penalty clause. You'll have the corrected contract by end of day today.\n\nApologies for the discrepancy.",
  "Thanks for sending this over. I'll review the key items and get back to you by end of day.\n\nLet me know if there's anything else you need in the meantime.",
  "Got it \u2014 I'll take a look at this and circle back with my thoughts. Appreciate you flagging it.",
]

export function ReplyComposer({ platform, onSend }: ReplyComposerProps) {
  const [content, setContent] = useState("")
  const [isTyping, setIsTyping] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const cancelRef = useRef(false)

  async function handleDraft() {
    if (isTyping) return
    cancelRef.current = false
    setIsTyping(true)
    setContent("")

    const draft = MOCK_DRAFTS[Math.floor(Math.random() * MOCK_DRAFTS.length)]

    // Typewriter effect
    for (let i = 0; i <= draft.length; i++) {
      if (cancelRef.current) break
      await new Promise((r) => setTimeout(r, 10 + Math.random() * 8))
      setContent(draft.slice(0, i))
    }

    if (!cancelRef.current) {
      setContent(draft)
    }
    setIsTyping(false)
  }

  function handleSend() {
    if (!content.trim() || isTyping) return
    onSend(content)
    setContent("")
    toast(`Sent via ${getPlatformName(platform)}`)
  }

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current
    if (el) {
      el.style.height = "auto"
      el.style.height = el.scrollHeight + "px"
    }
  }, [content])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cancelRef.current = true
    }
  }, [])

  return (
    <div className="border-t-2 border-foreground p-4">
      {/* Tone indicator */}
      <div className="text-[10px] font-mono text-muted-foreground mb-2 tracking-wider">
        {getPlatformName(platform)} tone: {TONE_MAP[platform] ?? "Default"}
      </div>

      {/* Textarea */}
      <textarea
        ref={textareaRef}
        value={content}
        onChange={(e) => {
          if (!isTyping) setContent(e.target.value)
        }}
        placeholder="Write a reply..."
        rows={3}
        className="w-full bg-transparent border-2 border-foreground/10 p-3 text-xs font-mono resize-none focus:outline-none focus:border-foreground/30 placeholder:text-muted-foreground/40 min-h-[80px] max-h-[200px]"
      />

      {/* Action bar */}
      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-3">
          <button
            onClick={handleDraft}
            disabled={isTyping}
            className={`flex items-center gap-1.5 px-3 py-1.5 border-2 text-[10px] font-mono tracking-wider uppercase transition-colors ${
              isTyping
                ? "border-[#ea580c]/30 text-[#ea580c]/60 cursor-wait"
                : "border-foreground/20 hover:border-[#ea580c] hover:text-[#ea580c]"
            }`}
          >
            <Sparkles
              size={12}
              className={isTyping ? "animate-pulse" : ""}
            />
            {isTyping ? "Drafting..." : "Draft with AI"}
          </button>
          <span className="text-[10px] font-mono text-muted-foreground">
            {content.length} chars
          </span>
        </div>

        <button
          onClick={handleSend}
          disabled={!content.trim() || isTyping}
          className={`flex items-center gap-1.5 px-4 py-1.5 text-[10px] font-mono tracking-wider uppercase transition-all ${
            content.trim() && !isTyping
              ? "bg-foreground text-background hover:opacity-90"
              : "bg-muted text-muted-foreground cursor-not-allowed"
          }`}
        >
          Send via {getPlatformName(platform)}
          <Send size={12} />
        </button>
      </div>
    </div>
  )
}
