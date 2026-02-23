"use client"

import { useState } from "react"
import { motion } from "framer-motion"
import { Star, Sparkles, Clock, Check } from "lucide-react"
import { toast } from "sonner"
import { useStore } from "@/lib/store"
import { PlatformIcon, getPlatformName } from "./platform-icon"
import { PriorityBadge } from "./priority-badge"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { Message } from "@/lib/types"

interface MessageCardProps {
  message: Message
  isSelected?: boolean
}

function relativeTime(date: Date): string {
  const diff = Date.now() - date.getTime()
  const min = Math.floor(diff / 60000)
  if (min < 1) return "now"
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  const days = Math.floor(hr / 24)
  if (days === 1) return "Yesterday"
  return `${days}d ago`
}

export function MessageCard({ message, isSelected }: MessageCardProps) {
  const { selectMessage, markDone, snoozeMessage, unsnooze } = useStore()
  const [isHovered, setIsHovered] = useState(false)

  function handleSnooze(hours: number, label: string) {
    const until = new Date(Date.now() + hours * 60 * 60 * 1000)
    snoozeMessage(message.id, until)
    toast(`Snoozed until ${label}`, {
      action: {
        label: "Undo",
        onClick: () => unsnooze(message.id),
      },
    })
  }

  function handleDone(e: React.MouseEvent) {
    e.stopPropagation()
    markDone(message.id)
    toast("Marked as done")
  }

  const initials = message.sender.name
    .split(" ")
    .map((n) => n[0])
    .join("")

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{
        opacity: 0,
        x: 40,
        height: 0,
        marginBottom: 0,
        paddingTop: 0,
        paddingBottom: 0,
        overflow: "hidden",
      }}
      transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={() => selectMessage(message.id)}
      className={`group relative border-2 p-4 cursor-pointer transition-colors duration-100 ${
        isSelected
          ? "border-[#ea580c] bg-orange-50/50 dark:bg-orange-950/10"
          : "border-foreground/10 hover:border-foreground/30 bg-background"
      } ${!message.isRead ? "border-l-[3px] border-l-[#ea580c]" : ""}`}
    >
      <div className="flex gap-3">
        {/* Platform icon */}
        <PlatformIcon platform={message.platform} size="md" />

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Row 1: sender + time + badge */}
          <div className="flex items-center gap-2 mb-1">
            <div className="flex items-center gap-1.5 min-w-0 flex-1">
              <div className="w-5 h-5 bg-muted flex items-center justify-center shrink-0">
                <span className="text-[8px] font-mono font-bold text-muted-foreground">
                  {initials}
                </span>
              </div>
              {message.sender.isVip && (
                <Star
                  size={10}
                  fill="#ea580c"
                  className="text-[#ea580c] shrink-0"
                />
              )}
              <span className="text-xs font-mono font-semibold truncate">
                {message.sender.name}
              </span>
              <span className="text-[10px] font-mono text-muted-foreground shrink-0 hidden sm:inline">
                via {getPlatformName(message.platform)}
              </span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-[10px] font-mono text-muted-foreground">
                {relativeTime(message.receivedAt)}
              </span>
              <PriorityBadge
                priority={message.priority}
                reason={message.priorityReason}
                showLabel={false}
              />
            </div>
          </div>

          {/* Subject */}
          {message.subject && (
            <p className="text-xs font-mono font-semibold truncate mb-0.5">
              {message.subject}
            </p>
          )}

          {/* Preview */}
          <p className="text-[11px] font-mono text-muted-foreground line-clamp-1">
            {message.preview.slice(0, 120)}
          </p>

          {/* AI context note */}
          <p className="text-[10px] font-mono italic text-muted-foreground/60 mt-1">
            {message.aiContextNote}
          </p>
        </div>
      </div>

      {/* Hover actions */}
      {isHovered && (
        <motion.div
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.1 }}
          className="absolute right-3 top-3 flex items-center gap-1.5 z-10"
        >
          <HoverButton
            icon={<Sparkles size={11} />}
            label="Draft Reply"
            onClick={(e) => {
              e.stopPropagation()
              selectMessage(message.id)
            }}
          />

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                onClick={(e) => e.stopPropagation()}
                className="flex items-center gap-1 px-2 py-1 border border-foreground/20 bg-background text-[10px] font-mono tracking-wider uppercase hover:bg-muted transition-colors"
              >
                <Clock size={11} />
                Snooze
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="end"
              className="font-mono border-2 border-foreground"
            >
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  handleSnooze(2, "in 2 hours")
                }}
                className="text-xs tracking-wider cursor-pointer"
              >
                In 2 hours
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  handleSnooze(14, "tomorrow morning")
                }}
                className="text-xs tracking-wider cursor-pointer"
              >
                Tomorrow morning
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation()
                  handleSnooze(168, "next week")
                }}
                className="text-xs tracking-wider cursor-pointer"
              >
                Next week
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <HoverButton icon={<Check size={11} />} label="Done" onClick={handleDone} />
        </motion.div>
      )}
    </motion.div>
  )
}

function HoverButton({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode
  label: string
  onClick: (e: React.MouseEvent) => void
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1 px-2 py-1 border border-foreground/20 bg-background text-[10px] font-mono tracking-wider uppercase hover:bg-muted transition-colors"
    >
      {icon}
      {label}
    </button>
  )
}
