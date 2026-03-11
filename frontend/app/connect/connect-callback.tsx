"use client"

import { useEffect, useRef } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Loader2, Check, AlertCircle } from "lucide-react"
import { useStore } from "@/lib/store"
import type { Platform } from "@/lib/types"

/**
 * Handles OAuth redirects from the backend:
 *   /connect?platform=gmail&status=success
 *   /connect?platform=slack&status=success
 *   /connect?platform=discord&status=success
 *   /connect?platform=...&status=error&detail=...
 */
export function ConnectCallback() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { connectPlatform } = useStore()
  const handled = useRef(false)

  const platform = searchParams.get("platform") as Platform | null
  const status = searchParams.get("status")
  const detail = searchParams.get("detail")

  useEffect(() => {
    if (handled.current) return
    handled.current = true

    if (platform && status === "success") {
      connectPlatform(platform)
      setTimeout(() => router.replace("/onboarding"), 1500)
    } else if (status === "error") {
      setTimeout(() => router.replace("/onboarding"), 3000)
    } else {
      router.replace("/onboarding")
    }
  }, [platform, status, connectPlatform, router])

  return (
    <div className="min-h-screen dot-grid-bg flex items-center justify-center px-4">
      <div className="w-full max-w-sm text-center space-y-4">
        {status === "success" ? (
          <>
            <div className="flex justify-center">
              <div className="border-2 border-green-500 p-3 inline-flex">
                <Check size={24} className="text-green-500" />
              </div>
            </div>
            <h1 className="text-sm font-mono font-bold tracking-wider uppercase">
              {platform} Connected
            </h1>
            <p className="text-[11px] font-mono text-muted-foreground">
              Redirecting to onboarding...
            </p>
          </>
        ) : status === "error" ? (
          <>
            <div className="flex justify-center">
              <div className="border-2 border-red-500 p-3 inline-flex">
                <AlertCircle size={24} className="text-red-500" />
              </div>
            </div>
            <h1 className="text-sm font-mono font-bold tracking-wider uppercase">
              Connection Failed
            </h1>
            <p className="text-[11px] font-mono text-muted-foreground">
              {detail || `Failed to connect ${platform}. Please try again.`}
            </p>
          </>
        ) : (
          <>
            <Loader2 size={24} className="animate-spin mx-auto text-muted-foreground" />
            <p className="text-[11px] font-mono text-muted-foreground">
              Processing...
            </p>
          </>
        )}
      </div>
    </div>
  )
}
