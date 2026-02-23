"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { motion } from "framer-motion"

const SYNC_LINES = [
  { text: "Initializing secure connections...", delay: 0 },
  { text: "Connecting to Gmail...", delay: 500 },
  { text: "Connecting to Slack...", delay: 900 },
  { text: "Fetching your last 7 days of messages...", delay: 1400 },
  { text: "Found 142 messages across 3 platforms.", delay: 2200 },
  { text: "Running AI classification pipeline...", delay: 2800 },
  { text: "Building your contact graph...", delay: 3400 },
  { text: "Scoring priority (6 weighted signals)...", delay: 3900 },
  { text: "Ranking by priority...", delay: 4400 },
  { text: "Your inbox is ready.", delay: 5000, highlight: true },
]

export default function SyncPage() {
  const router = useRouter()
  const [visibleLines, setVisibleLines] = useState(0)

  useEffect(() => {
    const timers: NodeJS.Timeout[] = []

    SYNC_LINES.forEach((line, i) => {
      timers.push(setTimeout(() => setVisibleLines(i + 1), line.delay))
    })

    // Auto-navigate after the last line + a short pause
    timers.push(setTimeout(() => router.push("/dashboard"), 5800))

    return () => timers.forEach(clearTimeout)
  }, [router])

  const progress = Math.round((visibleLines / SYNC_LINES.length) * 100)

  return (
    <div className="min-h-screen bg-foreground flex items-center justify-center px-4">
      <div className="w-full max-w-xl">
        {/* Terminal chrome */}
        <div className="flex items-center gap-3 border-b border-background/10 pb-3 mb-8">
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 bg-[#ea580c]" />
            <div className="w-2.5 h-2.5 bg-background/20" />
            <div className="w-2.5 h-2.5 bg-background/20" />
          </div>
          <span className="text-[10px] font-mono tracking-[0.2em] uppercase text-background/30">
            // SYNC: FIRST_RUN
          </span>
        </div>

        {/* Terminal lines */}
        <div className="space-y-2.5 font-mono text-sm min-h-[320px]">
          {SYNC_LINES.slice(0, visibleLines).map((line, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.25 }}
              className="flex items-start gap-3"
            >
              <span className="text-background/20 text-xs select-none w-6 text-right shrink-0 pt-px">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="text-[#ea580c] select-none shrink-0">
                {line.highlight ? "\u2713" : ">"}
              </span>
              <span
                className={
                  line.highlight
                    ? "text-[#ea580c] font-bold"
                    : "text-background/80"
                }
              >
                {line.text}
              </span>
              {i === visibleLines - 1 && !line.highlight && (
                <span className="inline-block w-1.5 h-4 bg-[#ea580c] animate-blink ml-0.5 mt-0.5" />
              )}
            </motion.div>
          ))}
        </div>

        {/* Progress bar */}
        <div className="mt-8">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-mono text-background/30 tracking-wider uppercase">
              Progress
            </span>
            <span className="text-[10px] font-mono text-background/30">
              {progress}%
            </span>
          </div>
          <div className="h-0.5 bg-background/10">
            <motion.div
              className="h-full bg-[#ea580c]"
              initial={{ width: "0%" }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
