"use client"

import { useState } from "react"
import { motion } from "framer-motion"
import {
  Trash2,
  Plus,
  X,
  Shield,
  Star,
} from "lucide-react"
import { useStore } from "@/lib/store"
import { PlatformIcon, getPlatformName } from "@/components/app/platform-icon"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Switch } from "@/components/ui/switch"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { ScrollArea } from "@/components/ui/scroll-area"
import { toast } from "sonner"

export default function SettingsPage() {
  return (
    <div className="flex flex-col h-screen">
      {/* Top bar */}
      <div className="px-6 py-4 border-b-2 border-foreground shrink-0">
        <h1 className="text-sm font-mono font-bold tracking-wider uppercase">
          Settings
        </h1>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-6 max-w-2xl">
          <Tabs defaultValue="platforms" className="w-full">
            <TabsList className="w-full justify-start bg-transparent border-2 border-foreground/10 p-0 h-auto">
              {["platforms", "vip", "notifications", "account"].map((tab) => (
                <TabsTrigger
                  key={tab}
                  value={tab}
                  className="flex-1 text-[11px] font-mono tracking-wider uppercase py-2.5 data-[state=active]:bg-foreground data-[state=active]:text-background rounded-none border-r border-foreground/10 last:border-r-0"
                >
                  {tab === "vip" ? "VIP Contacts" : tab}
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value="platforms" className="mt-6">
              <PlatformsTab />
            </TabsContent>
            <TabsContent value="vip" className="mt-6">
              <VipTab />
            </TabsContent>
            <TabsContent value="notifications" className="mt-6">
              <NotificationsTab />
            </TabsContent>
            <TabsContent value="account" className="mt-6">
              <AccountTab />
            </TabsContent>
          </Tabs>
        </div>
      </ScrollArea>
    </div>
  )
}

/* ── Tab 1: Platforms ─────────────────────────────────── */

function PlatformsTab() {
  const { platforms, connectPlatform, disconnectPlatform } = useStore()

  return (
    <div className="space-y-3">
      <p className="text-xs font-mono text-muted-foreground mb-4">
        Manage your connected communication platforms.
      </p>
      {platforms.map((p) => (
        <div
          key={p.platform}
          className={`border-2 p-4 flex items-center gap-4 ${
            p.isConnected
              ? "border-green-500/40"
              : p.isAvailable
                ? "border-foreground/10"
                : "border-border opacity-50"
          }`}
        >
          <PlatformIcon platform={p.platform} size="lg" showDot={p.isConnected} />
          <div className="flex-1 min-w-0">
            <span className="text-sm font-mono font-bold tracking-wider uppercase block">
              {p.displayName}
            </span>
            <span className="text-[10px] font-mono text-muted-foreground">
              {p.isConnected
                ? `Connected \u00b7 Last synced ${p.lastSynced ? "recently" : "never"}`
                : p.isAvailable
                  ? "Not connected"
                  : "Coming soon"}
            </span>
          </div>
          {p.isConnected ? (
            <button
              onClick={() => {
                disconnectPlatform(p.platform)
                toast(`Disconnected ${p.displayName}`)
              }}
              className="text-[10px] font-mono tracking-wider uppercase text-red-500 border border-red-500/30 px-3 py-1.5 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors"
            >
              Disconnect
            </button>
          ) : p.isAvailable ? (
            <button
              onClick={() => {
                connectPlatform(p.platform)
                toast(`Connected ${p.displayName}`)
              }}
              className="text-[10px] font-mono tracking-wider uppercase border-2 border-foreground bg-foreground text-background px-3 py-1.5 hover:opacity-90 transition-opacity"
            >
              Connect
            </button>
          ) : null}
        </div>
      ))}
    </div>
  )
}

/* ── Tab 2: VIP Contacts ──────────────────────────────── */

function VipTab() {
  const { vipContacts, removeVip } = useStore()
  const [newVip, setNewVip] = useState("")

  return (
    <div>
      <p className="text-xs font-mono text-muted-foreground mb-4">
        VIP contacts always rank highest regardless of message content.
      </p>

      {/* Add VIP */}
      <div className="flex items-center gap-2 mb-6">
        <Input
          value={newVip}
          onChange={(e) => setNewVip(e.target.value)}
          placeholder="Search by name or email..."
          className="flex-1 font-mono text-xs"
        />
        <button
          disabled={!newVip.trim()}
          className="flex items-center gap-1.5 px-3 py-2 border-2 border-foreground bg-foreground text-background text-[10px] font-mono tracking-wider uppercase hover:opacity-90 transition-opacity disabled:opacity-30 disabled:cursor-not-allowed"
        >
          <Plus size={12} />
          Add VIP
        </button>
      </div>

      {/* VIP list */}
      {vipContacts.length === 0 ? (
        <div className="text-center py-8">
          <Star size={24} className="mx-auto text-muted-foreground mb-2" />
          <p className="text-xs font-mono text-muted-foreground">
            No VIP contacts yet. Add contacts whose messages should always
            appear at the top.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {vipContacts.map((c) => (
            <motion.div
              key={c.id}
              layout
              className="border-2 border-foreground/10 p-3 flex items-center gap-3"
            >
              <div className="w-8 h-8 bg-muted flex items-center justify-center shrink-0">
                <span className="text-[10px] font-mono font-bold">
                  {c.name
                    .split(" ")
                    .map((n) => n[0])
                    .join("")}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <span className="text-xs font-mono font-semibold block truncate">
                  {c.name}
                </span>
                <div className="flex items-center gap-2 mt-0.5">
                  <PlatformIcon platform={c.platform} size="sm" />
                  <span className="text-[10px] font-mono text-muted-foreground">
                    {c.email ?? getPlatformName(c.platform)}
                  </span>
                </div>
              </div>
              <button
                onClick={() => {
                  removeVip(c.id)
                  toast(`Removed ${c.name} from VIP`)
                }}
                className="p-1.5 text-muted-foreground hover:text-red-500 transition-colors"
              >
                <X size={14} />
              </button>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── Tab 3: Notifications ─────────────────────────────── */

function NotificationsTab() {
  const { notificationSettings, updateNotificationSettings } = useStore()

  return (
    <div className="space-y-6">
      <p className="text-xs font-mono text-muted-foreground">
        Configure how and when you receive notifications.
      </p>

      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <Label className="text-xs font-mono font-semibold">
              Push Notifications
            </Label>
            <p className="text-[10px] font-mono text-muted-foreground mt-0.5">
              Receive browser push notifications for new messages
            </p>
          </div>
          <Switch
            checked={notificationSettings.pushEnabled}
            onCheckedChange={(v) =>
              updateNotificationSettings({ pushEnabled: v })
            }
          />
        </div>

        <Separator />

        <div className="flex items-center justify-between">
          <div>
            <Label className="text-xs font-mono font-semibold">
              Urgent Only
            </Label>
            <p className="text-[10px] font-mono text-muted-foreground mt-0.5">
              Only notify for urgent messages (ignore Action + FYI)
            </p>
          </div>
          <Switch
            checked={notificationSettings.urgentOnly}
            onCheckedChange={(v) =>
              updateNotificationSettings({ urgentOnly: v })
            }
          />
        </div>

        <Separator />

        <div>
          <Label className="text-xs font-mono font-semibold mb-3 block">
            Quiet Hours
          </Label>
          <p className="text-[10px] font-mono text-muted-foreground mb-3">
            No notifications during this time window.
          </p>
          <div className="flex items-center gap-3">
            <div>
              <Label className="text-[10px] font-mono text-muted-foreground">
                From
              </Label>
              <Input
                type="time"
                value={notificationSettings.quietHoursStart}
                onChange={(e) =>
                  updateNotificationSettings({
                    quietHoursStart: e.target.value,
                  })
                }
                className="mt-1 font-mono text-xs w-32"
              />
            </div>
            <span className="text-muted-foreground mt-5">&mdash;</span>
            <div>
              <Label className="text-[10px] font-mono text-muted-foreground">
                To
              </Label>
              <Input
                type="time"
                value={notificationSettings.quietHoursEnd}
                onChange={(e) =>
                  updateNotificationSettings({ quietHoursEnd: e.target.value })
                }
                className="mt-1 font-mono text-xs w-32"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ── Tab 4: Account ───────────────────────────────────── */

function AccountTab() {
  const { user } = useStore()
  const [name, setName] = useState(user?.name ?? "")
  const [email, setEmail] = useState(user?.email ?? "")

  return (
    <div className="space-y-6">
      <p className="text-xs font-mono text-muted-foreground">
        Manage your account details and security.
      </p>

      <div className="space-y-4">
        <div>
          <Label className="text-[10px] font-mono tracking-wider uppercase">
            Name
          </Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1.5 font-mono text-xs"
          />
        </div>
        <div>
          <Label className="text-[10px] font-mono tracking-wider uppercase">
            Email
          </Label>
          <Input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1.5 font-mono text-xs"
          />
        </div>
        <div>
          <Label className="text-[10px] font-mono tracking-wider uppercase">
            Avatar
          </Label>
          <div className="flex items-center gap-3 mt-1.5">
            <div className="w-12 h-12 bg-muted border-2 border-foreground flex items-center justify-center">
              <span className="text-sm font-mono font-bold">
                {user?.name
                  ?.split(" ")
                  .map((n) => n[0])
                  .join("") ?? "?"}
              </span>
            </div>
            <button className="text-[10px] font-mono tracking-wider uppercase border border-foreground/20 px-3 py-1.5 hover:bg-muted transition-colors">
              Upload
            </button>
          </div>
        </div>

        <button
          onClick={() => toast("Profile updated")}
          className="border-2 border-foreground bg-foreground text-background px-4 py-2 text-[10px] font-mono tracking-wider uppercase hover:opacity-90 transition-opacity"
        >
          Save Changes
        </button>
      </div>

      <Separator />

      {/* Change password */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Shield size={14} />
          <span className="text-xs font-mono font-bold tracking-wider uppercase">
            Change Password
          </span>
        </div>
        <div>
          <Label className="text-[10px] font-mono tracking-wider uppercase">
            Current Password
          </Label>
          <Input
            type="password"
            placeholder="\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
            className="mt-1.5 font-mono text-xs"
          />
        </div>
        <div>
          <Label className="text-[10px] font-mono tracking-wider uppercase">
            New Password
          </Label>
          <Input
            type="password"
            placeholder="\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
            className="mt-1.5 font-mono text-xs"
          />
        </div>
        <button
          onClick={() => toast("Password updated")}
          className="border-2 border-foreground/20 px-4 py-2 text-[10px] font-mono tracking-wider uppercase hover:bg-muted transition-colors"
        >
          Update Password
        </button>
      </div>

      <Separator />

      {/* Danger zone */}
      <div className="border-2 border-red-500/30 p-4">
        <div className="flex items-center gap-2 mb-2">
          <Trash2 size={14} className="text-red-500" />
          <span className="text-xs font-mono font-bold tracking-wider uppercase text-red-500">
            Danger Zone
          </span>
        </div>
        <p className="text-[10px] font-mono text-muted-foreground mb-3">
          Permanently delete your account and all associated data. This action
          cannot be undone.
        </p>
        <button
          onClick={() => toast.error("This action requires confirmation")}
          className="text-[10px] font-mono tracking-wider uppercase text-red-500 border border-red-500/30 px-3 py-1.5 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors"
        >
          Delete Account
        </button>
      </div>
    </div>
  )
}
