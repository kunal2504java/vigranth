"use client"

import type { Platform } from "@/lib/types"

const PLATFORM_CONFIG: Record<Platform, { letter: string; color: string; bg: string }> = {
  gmail: { letter: "G", color: "#EA4335", bg: "rgba(234,67,53,0.12)" },
  slack: { letter: "S", color: "#611F69", bg: "rgba(97,31,105,0.12)" },
  discord: { letter: "D", color: "#5865F2", bg: "rgba(88,101,242,0.12)" },
  telegram: { letter: "T", color: "#0088CC", bg: "rgba(0,136,204,0.12)" },
  whatsapp: { letter: "W", color: "#25D366", bg: "rgba(37,211,102,0.12)" },
  outlook: { letter: "O", color: "#0078D4", bg: "rgba(0,120,212,0.12)" },
}

interface PlatformIconProps {
  platform: Platform
  size?: "sm" | "md" | "lg"
  showDot?: boolean
}

const sizeClasses = {
  sm: "w-6 h-6 text-[10px]",
  md: "w-8 h-8 text-xs",
  lg: "w-10 h-10 text-sm",
}

export function PlatformIcon({ platform, size = "md", showDot }: PlatformIconProps) {
  const config = PLATFORM_CONFIG[platform]
  if (!config) return null

  return (
    <div className="relative">
      <div
        className={`${sizeClasses[size]} flex items-center justify-center font-mono font-bold border-2 shrink-0`}
        style={{
          color: config.color,
          borderColor: config.color,
          backgroundColor: config.bg,
        }}
      >
        {config.letter}
      </div>
      {showDot && (
        <div
          className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 border border-background"
          style={{ backgroundColor: config.color, borderRadius: "50%" }}
        />
      )}
    </div>
  )
}

export function getPlatformColor(platform: Platform): string {
  return PLATFORM_CONFIG[platform]?.color ?? "#888"
}

export function getPlatformName(platform: Platform): string {
  const names: Record<Platform, string> = {
    gmail: "Gmail",
    slack: "Slack",
    discord: "Discord",
    telegram: "Telegram",
    whatsapp: "WhatsApp",
    outlook: "Outlook",
  }
  return names[platform] ?? platform
}
