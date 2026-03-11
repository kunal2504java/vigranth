"use client"

import { useState, useRef } from "react"
import { useRouter } from "next/navigation"
import { motion, AnimatePresence } from "framer-motion"
import { Check, ArrowRight, Inbox, Loader2, Phone, KeyRound, AlertCircle } from "lucide-react"
import { useStore } from "@/lib/store"
import { useAuthGuard } from "@/hooks/use-auth-guard"
import { PlatformIcon } from "@/components/app/platform-icon"
import { telegram as telegramApi, getOAuthConnectUrl } from "@/lib/api"
import type { Platform } from "@/lib/types"

// ── Telegram OTP flow state ─────────────────────────────────

type TelegramStep = "idle" | "phone" | "otp" | "connecting" | "done"

interface TelegramState {
  step: TelegramStep
  phone: string
  phoneCodeHash: string
  session: string
  code: string
  error: string | null
  loading: boolean
}

const initialTelegramState: TelegramState = {
  step: "idle",
  phone: "",
  phoneCodeHash: "",
  session: "",
  code: "",
  error: null,
  loading: false,
}

// ── Page ────────────────────────────────────────────────────

export default function OnboardingPage() {
  const router = useRouter()
  const { ready } = useAuthGuard()
  const { platforms, connectPlatform, connectedCount } = useStore()
  const [connecting, setConnecting] = useState<Platform | null>(null)

  // Telegram-specific state
  const [tg, setTg] = useState<TelegramState>(initialTelegramState)
  const otpInputRef = useRef<HTMLInputElement>(null)

  // ── Generic connect (non-Telegram) ──────────────────────

  function handleConnect(platform: Platform) {
    if (platform === "telegram") {
      setTg({ ...initialTelegramState, step: "phone" })
      return
    }

    // OAuth platforms — redirect to backend which redirects to consent screen
    if (platform === "gmail" || platform === "slack" || platform === "discord") {
      const url = getOAuthConnectUrl(platform)
      if (url) {
        window.location.href = url
      }
      return
    }

    // Unsupported platforms — no-op
  }

  // ── Telegram Step 1: Send OTP ───────────────────────────

  async function handleTelegramSendCode() {
    const phone = tg.phone.trim()
    if (!phone) {
      setTg((prev) => ({ ...prev, error: "Enter your phone number" }))
      return
    }
    setTg((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const res = await telegramApi.sendCode(phone)
      setTg((prev) => ({
        ...prev,
        step: "otp",
        phoneCodeHash: res.phone_code_hash,
        session: res.session,
        loading: false,
      }))
      // Auto-focus OTP input
      setTimeout(() => otpInputRef.current?.focus(), 100)
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to send code"
      setTg((prev) => ({ ...prev, loading: false, error: msg }))
    }
  }

  // ── Telegram Step 2: Verify OTP ─────────────────────────

  async function handleTelegramVerify() {
    const code = tg.code.trim()
    if (!code) {
      setTg((prev) => ({ ...prev, error: "Enter the code from Telegram" }))
      return
    }
    setTg((prev) => ({ ...prev, loading: true, error: null }))
    try {
      await telegramApi.verifyCode(
        tg.phone.trim(),
        code,
        tg.phoneCodeHash,
        tg.session
      )
      setTg((prev) => ({ ...prev, step: "done", loading: false }))
      connectPlatform("telegram")
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Verification failed"
      setTg((prev) => ({ ...prev, loading: false, error: msg }))
    }
  }

  // ── Cancel Telegram flow ────────────────────────────────

  function cancelTelegram() {
    setTg(initialTelegramState)
  }

  // ── Check if Telegram is in active auth flow ────────────

  const telegramActive = tg.step !== "idle" && tg.step !== "done"

  if (!ready) {
    return (
      <div className="min-h-screen dot-grid-bg flex items-center justify-center">
        <Loader2 size={24} className="animate-spin text-muted-foreground" />
      </div>
    )
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
          {platforms.map((p, i) => {
            const isTelegram = p.platform === "telegram"
            const showTelegramFlow = isTelegram && telegramActive

            return (
              <motion.div
                key={p.platform}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.1 + i * 0.08, ease: [0.22, 1, 0.36, 1] }}
              >
                <div
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
                        disabled={connecting !== null || (isTelegram && telegramActive)}
                        className="border-2 border-foreground bg-foreground text-background px-4 py-2 text-[11px] font-mono tracking-wider uppercase hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-wait flex items-center gap-2"
                      >
                        {connecting === p.platform && (
                          <Loader2 size={12} className="animate-spin" />
                        )}
                        {connecting === p.platform ? "Connecting..." : "Connect"}
                      </button>
                    ) : null}
                  </div>
                </div>

                {/* Telegram inline auth form */}
                <AnimatePresence>
                  {showTelegramFlow && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
                      className="overflow-hidden"
                    >
                      <div className="border-2 border-t-0 border-foreground bg-background p-4 space-y-3">
                        {/* Step indicator */}
                        <div className="flex items-center gap-2 text-[10px] font-mono tracking-wider uppercase text-muted-foreground">
                          <span className={tg.step === "phone" ? "text-foreground font-bold" : ""}>
                            1. Phone
                          </span>
                          <span>/</span>
                          <span className={tg.step === "otp" ? "text-foreground font-bold" : ""}>
                            2. Verify OTP
                          </span>
                        </div>

                        {/* Phone input step */}
                        {tg.step === "phone" && (
                          <div className="space-y-2">
                            <div className="flex gap-2">
                              <div className="relative flex-1">
                                <Phone size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                                <input
                                  type="tel"
                                  placeholder="+91 98765 43210"
                                  value={tg.phone}
                                  onChange={(e) => setTg((prev) => ({ ...prev, phone: e.target.value, error: null }))}
                                  onKeyDown={(e) => e.key === "Enter" && handleTelegramSendCode()}
                                  autoFocus
                                  className="w-full border-2 border-foreground bg-background pl-9 pr-3 py-2 text-xs font-mono placeholder:text-muted-foreground/50 focus:outline-none focus:ring-0"
                                />
                              </div>
                              <button
                                onClick={handleTelegramSendCode}
                                disabled={tg.loading}
                                className="border-2 border-foreground bg-foreground text-background px-4 py-2 text-[11px] font-mono tracking-wider uppercase hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-2 shrink-0"
                              >
                                {tg.loading ? <Loader2 size={12} className="animate-spin" /> : null}
                                Send OTP
                              </button>
                            </div>
                            <p className="text-[10px] font-mono text-muted-foreground">
                              We&apos;ll send a login code to your Telegram app.
                            </p>
                          </div>
                        )}

                        {/* OTP input step */}
                        {tg.step === "otp" && (
                          <div className="space-y-2">
                            <div className="flex gap-2">
                              <div className="relative flex-1">
                                <KeyRound size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                                <input
                                  ref={otpInputRef}
                                  type="text"
                                  placeholder="Enter code"
                                  value={tg.code}
                                  onChange={(e) => setTg((prev) => ({ ...prev, code: e.target.value, error: null }))}
                                  onKeyDown={(e) => e.key === "Enter" && handleTelegramVerify()}
                                  autoFocus
                                  className="w-full border-2 border-foreground bg-background pl-9 pr-3 py-2 text-xs font-mono tracking-[0.3em] placeholder:tracking-normal placeholder:text-muted-foreground/50 focus:outline-none focus:ring-0"
                                />
                              </div>
                              <button
                                onClick={handleTelegramVerify}
                                disabled={tg.loading}
                                className="border-2 border-foreground bg-foreground text-background px-4 py-2 text-[11px] font-mono tracking-wider uppercase hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-2 shrink-0"
                              >
                                {tg.loading ? <Loader2 size={12} className="animate-spin" /> : null}
                                Verify
                              </button>
                            </div>
                            <p className="text-[10px] font-mono text-muted-foreground">
                              Check Telegram for a login code sent to <span className="text-foreground">{tg.phone}</span>
                            </p>
                          </div>
                        )}

                        {/* Error display */}
                        {tg.error && (
                          <div className="flex items-center gap-2 text-[11px] font-mono text-red-500">
                            <AlertCircle size={12} />
                            {tg.error}
                          </div>
                        )}

                        {/* Cancel button */}
                        <button
                          onClick={cancelTelegram}
                          className="text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
                        >
                          cancel
                        </button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            )
          })}
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
