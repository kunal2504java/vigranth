"use client"

import { useRouter, usePathname } from "next/navigation"
import {
  Inbox,
  AlertTriangle,
  Bell,
  MessageCircle,
  Clock,
  Plus,
  Settings,
  Keyboard,
  LogOut,
} from "lucide-react"
import { useStore } from "@/lib/store"
import { PlatformIcon, getPlatformName } from "./platform-icon"
import { Separator } from "@/components/ui/separator"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"

export function Sidebar() {
  const router = useRouter()
  const pathname = usePathname()
  const {
    user,
    logout,
    activeFilter,
    setActiveFilter,
    urgentCount,
    actionCount,
    snoozedCount,
    totalUnread,
    platforms,
  } = useStore()

  const isSettings = pathname === "/dashboard/settings"
  const connectedPlatforms = platforms.filter((p) => p.isConnected)

  function navTo(filter: string) {
    setActiveFilter(filter as typeof activeFilter)
    if (isSettings) router.push("/dashboard")
  }

  return (
    <div className="w-60 border-r-2 border-foreground bg-background flex flex-col h-screen shrink-0">
      {/* ── Top: Logo + Avatar ───────────────────────── */}
      <div className="px-4 py-4 border-b-2 border-foreground flex items-center gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Inbox
            size={16}
            strokeWidth={1.5}
            className="text-[#ea580c] shrink-0"
          />
          <span className="text-xs font-mono font-bold tracking-[0.12em] uppercase truncate">
            ZENVO
          </span>
        </div>
        <Avatar className="w-7 h-7 border border-foreground shrink-0">
          <AvatarFallback className="text-[10px] font-mono font-bold bg-muted">
            {user?.name
              ?.split(" ")
              .map((n) => n[0])
              .join("") ?? "?"}
          </AvatarFallback>
        </Avatar>
      </div>

      {/* ── Navigation ───────────────────────────────── */}
      <div className="flex-1 overflow-y-auto py-3">
        {/* INBOX */}
        <SectionLabel>Inbox</SectionLabel>
        <NavItem
          icon={<Inbox size={14} />}
          label="All Messages"
          count={totalUnread}
          active={!isSettings && activeFilter === "all"}
          onClick={() => navTo("all")}
        />
        <NavItem
          icon={<AlertTriangle size={14} />}
          label="Urgent"
          count={urgentCount}
          active={!isSettings && activeFilter === "urgent"}
          onClick={() => navTo("urgent")}
          accent="red"
        />
        <NavItem
          icon={<Bell size={14} />}
          label="Action Needed"
          count={actionCount}
          active={!isSettings && activeFilter === "action_needed"}
          onClick={() => navTo("action_needed")}
          accent="amber"
        />
        <NavItem
          icon={<MessageCircle size={14} />}
          label="FYI"
          active={!isSettings && activeFilter === "fyi"}
          onClick={() => navTo("fyi")}
        />
        <NavItem
          icon={<Clock size={14} />}
          label="Snoozed"
          count={snoozedCount || undefined}
          active={!isSettings && activeFilter === "snoozed"}
          onClick={() => navTo("snoozed")}
        />

        <Separator className="my-3" />

        {/* PLATFORMS */}
        <SectionLabel>Platforms</SectionLabel>
        {connectedPlatforms.map((p) => (
          <NavItem
            key={p.platform}
            icon={<PlatformIcon platform={p.platform} size="sm" showDot />}
            label={getPlatformName(p.platform)}
            active={!isSettings && activeFilter === p.platform}
            onClick={() => navTo(p.platform)}
            iconRaw
          />
        ))}
        <NavItem
          icon={<Plus size={14} className="text-muted-foreground" />}
          label="Add Platform"
          onClick={() => router.push("/dashboard/settings")}
          muted
        />
      </div>

      {/* ── Bottom ───────────────────────────────────── */}
      <div className="border-t-2 border-foreground">
        <NavItem
          icon={<Settings size={14} />}
          label="Settings"
          active={isSettings}
          onClick={() => router.push("/dashboard/settings")}
        />
        <NavItem
          icon={<Keyboard size={14} />}
          label="Shortcuts"
          shortcut="?"
          onClick={() =>
            document.dispatchEvent(new CustomEvent("toggle-shortcuts"))
          }
        />
        <NavItem
          icon={<LogOut size={14} />}
          label="Log Out"
          onClick={() => {
            logout()
            router.push("/")
          }}
          muted
        />
      </div>
    </div>
  )
}

/* ── Helpers ──────────────────────────────────────────── */

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-4 mb-1 mt-1">
      <span className="text-[9px] font-mono tracking-[0.2em] uppercase text-muted-foreground">
        {children}
      </span>
    </div>
  )
}

interface NavItemProps {
  icon: React.ReactNode
  label: string
  count?: number
  active?: boolean
  onClick: () => void
  accent?: "red" | "amber"
  shortcut?: string
  muted?: boolean
  iconRaw?: boolean
}

function NavItem({
  icon,
  label,
  count,
  active,
  onClick,
  accent,
  shortcut,
  muted,
  iconRaw,
}: NavItemProps) {
  const accentColor =
    accent === "red"
      ? "text-red-500"
      : accent === "amber"
        ? "text-amber-500"
        : ""

  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2.5 px-4 py-2 text-left transition-colors duration-100 ${
        active
          ? "bg-foreground text-background"
          : muted
            ? "text-muted-foreground hover:text-foreground hover:bg-muted/50"
            : "text-foreground hover:bg-muted/50"
      }`}
    >
      <span className={`shrink-0 ${active ? "" : accentColor}`}>
        {iconRaw ? (
          icon
        ) : (
          <span className="flex items-center justify-center w-5 h-5">
            {icon}
          </span>
        )}
      </span>
      <span className="flex-1 text-[11px] font-mono tracking-wider truncate">
        {label}
      </span>
      {count !== undefined && count > 0 && (
        <span
          className={`text-[9px] font-mono font-bold px-1.5 py-0.5 shrink-0 ${
            active ? "bg-background/20 text-background" : "bg-muted text-muted-foreground"
          }`}
        >
          {count}
        </span>
      )}
      {shortcut && (
        <span className="text-[9px] font-mono text-muted-foreground border border-border px-1 py-0.5 shrink-0">
          {shortcut}
        </span>
      )}
    </button>
  )
}
