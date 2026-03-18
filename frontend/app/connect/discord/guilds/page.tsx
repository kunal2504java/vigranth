"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { motion, AnimatePresence } from "framer-motion"
import { Check, ExternalLink, Loader2, RefreshCw, ServerCrash, ShieldCheck } from "lucide-react"
import { discord, type DiscordGuild } from "@/lib/api"
import { useAuthGuard } from "@/hooks/use-auth-guard"

function guildIconUrl(guild: DiscordGuild): string | null {
  if (!guild.icon) return null
  return `https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png?size=64`
}

function GuildAvatar({ guild }: { guild: DiscordGuild }) {
  const url = guildIconUrl(guild)
  if (url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={url}
        alt={guild.name}
        className="w-10 h-10 object-cover border border-border"
      />
    )
  }
  // Fallback: first two chars of guild name
  const initials = guild.name.slice(0, 2).toUpperCase()
  return (
    <div className="w-10 h-10 border border-border bg-muted flex items-center justify-center text-[11px] font-mono font-bold">
      {initials}
    </div>
  )
}

export default function DiscordGuildsPage() {
  const router = useRouter()
  const { ready } = useAuthGuard()
  const [guilds, setGuilds] = useState<DiscordGuild[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [addingGuildId, setAddingGuildId] = useState<string | null>(null)

  const fetchGuilds = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    else setRefreshing(true)
    setError(null)
    try {
      const data = await discord.guilds()
      setGuilds(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load servers")
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => {
    if (ready) fetchGuilds()
  }, [ready, fetchGuilds])

  function handleAddBot(guild: DiscordGuild) {
    setAddingGuildId(guild.id)
    // Open invite in new tab; user will come back here after authorizing
    window.open(guild.invite_url, "_blank", "width=500,height=700")
    // Poll for bot presence after a short delay to auto-refresh
    setTimeout(() => {
      fetchGuilds(true)
      setAddingGuildId(null)
    }, 5000)
  }

  const connectedCount = guilds.filter((g) => g.bot_in_guild).length

  if (!ready || loading) {
    return (
      <div className="min-h-screen dot-grid-bg flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={20} className="animate-spin text-muted-foreground" />
          <p className="text-[11px] font-mono text-muted-foreground tracking-wider uppercase">
            Loading your servers...
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen dot-grid-bg flex items-center justify-center px-4 py-12">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-lg"
      >
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-1">
            {/* Discord blurple dot */}
            <span className="w-2 h-2 bg-[#5865F2]" />
            <span className="text-[10px] font-mono tracking-[0.2em] uppercase text-muted-foreground">
              Discord
            </span>
          </div>
          <h1 className="text-lg font-mono font-bold tracking-wider uppercase">
            Select Your Servers
          </h1>
          <p className="text-[11px] font-mono text-muted-foreground mt-1">
            Add the UnifyInbox bot to servers you want to monitor.
            The bot can only read channels you give it access to.
          </p>
        </div>

        {/* Status bar */}
        {connectedCount > 0 && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            className="border border-[#5865F2]/40 bg-[#5865F2]/5 px-3 py-2 mb-4 flex items-center gap-2"
          >
            <ShieldCheck size={12} className="text-[#5865F2] shrink-0" />
            <span className="text-[11px] font-mono text-[#5865F2]">
              Bot active in {connectedCount} server{connectedCount !== 1 ? "s" : ""}
            </span>
          </motion.div>
        )}

        {/* Error */}
        {error && (
          <div className="border border-red-500/40 bg-red-500/5 px-3 py-2 mb-4 flex items-center gap-2">
            <ServerCrash size={12} className="text-red-500 shrink-0" />
            <span className="text-[11px] font-mono text-red-500">{error}</span>
          </div>
        )}

        {/* Guild list */}
        <div className="space-y-2 mb-6">
          <AnimatePresence initial={false}>
            {guilds.map((guild, i) => (
              <motion.div
                key={guild.id}
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.04, ease: [0.22, 1, 0.36, 1] }}
                className={`border-2 p-3 flex items-center gap-3 transition-colors ${
                  guild.bot_in_guild
                    ? "border-[#5865F2]/50 bg-[#5865F2]/5"
                    : "border-border bg-background"
                }`}
              >
                <GuildAvatar guild={guild} />

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-mono font-bold truncate">
                      {guild.name}
                    </span>
                    {guild.owner && (
                      <span className="text-[9px] font-mono tracking-wider uppercase border border-border px-1 py-0.5 text-muted-foreground shrink-0">
                        Owner
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] font-mono text-muted-foreground mt-0.5">
                    {guild.bot_in_guild ? "Bot is active in this server" : "Bot not added yet"}
                  </p>
                </div>

                <div className="shrink-0">
                  {guild.bot_in_guild ? (
                    <span className="flex items-center gap-1.5 text-[#5865F2] text-[11px] font-mono tracking-wider uppercase">
                      <Check size={13} strokeWidth={2.5} />
                      Active
                    </span>
                  ) : (
                    <button
                      onClick={() => handleAddBot(guild)}
                      disabled={addingGuildId === guild.id}
                      className="border-2 border-foreground bg-foreground text-background px-3 py-1.5 text-[11px] font-mono tracking-wider uppercase hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-1.5"
                    >
                      {addingGuildId === guild.id ? (
                        <Loader2 size={11} className="animate-spin" />
                      ) : (
                        <ExternalLink size={11} />
                      )}
                      Add Bot
                    </button>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {guilds.length === 0 && !error && (
            <div className="border-2 border-dashed border-border p-8 text-center">
              <p className="text-[11px] font-mono text-muted-foreground">
                No Discord servers found.
              </p>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchGuilds(true)}
            disabled={refreshing}
            className="border-2 border-border px-4 py-2.5 text-[11px] font-mono tracking-wider uppercase hover:border-foreground transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <RefreshCw size={12} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>

          <button
            onClick={() => router.push("/onboarding")}
            className="flex-1 border-2 border-foreground bg-foreground text-background px-4 py-2.5 text-[11px] font-mono tracking-wider uppercase hover:opacity-90 transition-opacity"
          >
            {connectedCount > 0 ? "Done" : "Skip for now"}
          </button>
        </div>

        <p className="text-[10px] font-mono text-muted-foreground mt-4 text-center">
          After adding the bot, click <span className="text-foreground">Refresh</span> to confirm it joined.
        </p>
      </motion.div>
    </div>
  )
}
