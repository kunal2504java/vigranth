"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { motion } from "framer-motion"
import { Check, ArrowRight, Inbox, Loader2 } from "lucide-react"
import { useStore } from "@/lib/store"
import { PlatformIcon } from "@/components/app/platform-icon"
import type { Platform } from "@/lib/types"

export default function OnboardingPage() {
  const router = useRouter()
  const { platforms, connectPlatform, connectedCount } = useStore()
  const [connecting, setConnecting] = useState<Platform | null>(null)

  function handleConnect(platform: Platform) {
    setConnecting(platform)
    // Simulate OAuth popup flow
    setTimeout(() => {
      connectPlatform(platform)
      setConnecting(null)
    }, 1200)
  }

  return (
    <div className="min-h-screen dot-grid-bg flex items-center justify-center px-4 py-12">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        className="w-full max-w-lg"
      >
        {/* Logo */}
        <div className="flex items-center gap-3 mb-6">
          <Inbox size={20} strokeWidth={1.5} />
          <span className="text-sm font-mono tracking-[0.15em] uppercase font-bold">
            UNIFYINBOX
          </span>
        </div>

        {/* Header */}
        <h1 className="text-lg font-mono font-bold tracking-wider uppercase mb-1">
          Connect Your Platforms
        </h1>
        <p className="text-xs font-mono text-muted-foreground mb-8">
          Connect your platforms. We&apos;ll handle the rest.
        </p>

        {/* Platform checklist */}
        <div className="space-y-3 mb-10">
          {platforms.map((p, i) => (
            <motion.div
              key={p.platform}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.1 + i * 0.08, ease: [0.22, 1, 0.36, 1] }}
              className={`border-2 p-4 flex items-center gap-4 transition-colors duration-300 ${
                p.isConnected
                  ? "border-green-500/60 bg-green-50/40 dark:bg-green-950/20"
                  : p.isAvailable
                    ? "border-foreground bg-background"
                    : "border-border bg-muted/20 opacity-50"
              }`}
            >
              <PlatformIcon
                platform={p.platform}
                size="lg"
                showDot={p.isConnected}
              />

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-mono font-bold tracking-wider uppercase">
                    {p.displayName}
                  </span>
                  {!p.isAvailable && (
                    <span className="text-[9px] font-mono tracking-wider uppercase text-muted-foreground border border-border px-1.5 py-0.5">
                      Coming Soon
                    </span>
                  )}
                </div>
                <p className="text-[11px] font-mono text-muted-foreground mt-0.5 truncate">
                  {p.description}
                </p>
              </div>

              <div className="shrink-0">
                {p.isConnected ? (
                  <motion.span
                    initial={{ scale: 0.8, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    className="flex items-center gap-1.5 text-green-600 dark:text-green-400 text-[11px] font-mono tracking-wider uppercase"
                  >
                    <Check size={14} strokeWidth={2.5} />
                    Connected
                  </motion.span>
                ) : p.isAvailable ? (
                  <button
                    onClick={() => handleConnect(p.platform)}
                    disabled={connecting !== null}
                    className="border-2 border-foreground bg-foreground text-background px-4 py-2 text-[11px] font-mono tracking-wider uppercase hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-wait flex items-center gap-2"
                  >
                    {connecting === p.platform && (
                      <Loader2 size={12} className="animate-spin" />
                    )}
                    {connecting === p.platform ? "Connecting..." : "Connect"}
                  </button>
                ) : null}
              </div>
            </motion.div>
          ))}
        </div>

        {/* Actions */}
        <div className="flex flex-col items-center gap-4">
          <button
            onClick={() => router.push("/sync")}
            disabled={connectedCount === 0}
            className={`w-full flex items-center justify-center gap-2 border-2 px-4 py-3.5 text-xs font-mono tracking-wider uppercase transition-all duration-200 ${
              connectedCount > 0
                ? "border-foreground bg-foreground text-background hover:opacity-90 cursor-pointer"
                : "border-border text-muted-foreground cursor-not-allowed"
            }`}
          >
            Continue to Zenvo
            <ArrowRight size={14} />
          </button>

          <button
            onClick={() => router.push("/sync")}
            className="text-[10px] font-mono text-muted-foreground/60 hover:text-muted-foreground transition-colors"
          >
            skip for now
          </button>
        </div>
      </motion.div>
    </div>
  )
}
