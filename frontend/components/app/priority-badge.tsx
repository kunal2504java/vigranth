"use client"

import type { Priority } from "@/lib/types"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

const PRIORITY_CONFIG: Record<Priority, { label: string; icon: string; className: string }> = {
  urgent: {
    label: "Urgent",
    icon: "\u{1F534}",
    className: "border-red-500 text-red-600 bg-red-50 dark:bg-red-950/30",
  },
  action_needed: {
    label: "Action Needed",
    icon: "\u{1F7E1}",
    className: "border-amber-500 text-amber-600 bg-amber-50 dark:bg-amber-950/30",
  },
  fyi: {
    label: "FYI",
    icon: "\u{1F4AC}",
    className: "border-blue-400 text-blue-500 bg-blue-50 dark:bg-blue-950/30",
  },
  noise: {
    label: "Noise",
    icon: "\u{1F515}",
    className: "border-gray-400 text-gray-500 bg-gray-50 dark:bg-gray-900/30",
  },
}

interface PriorityBadgeProps {
  priority: Priority
  reason?: string
  showLabel?: boolean
}

export function PriorityBadge({ priority, reason, showLabel = true }: PriorityBadgeProps) {
  const config = PRIORITY_CONFIG[priority]
  if (!config) return null

  const badge = (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 border text-[10px] font-mono tracking-wider uppercase shrink-0 ${config.className}`}
    >
      <span>{config.icon}</span>
      {showLabel && <span>{config.label}</span>}
    </span>
  )

  if (reason) {
    return (
      <TooltipProvider delayDuration={300}>
        <Tooltip>
          <TooltipTrigger asChild>{badge}</TooltipTrigger>
          <TooltipContent
            side="top"
            className="max-w-xs font-mono text-xs border-2 border-foreground"
          >
            <p className="text-[10px] tracking-wider uppercase text-muted-foreground mb-1">
              AI Reasoning
            </p>
            <p>{reason}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    )
  }

  return badge
}
