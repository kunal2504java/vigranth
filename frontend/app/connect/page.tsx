"use client"

import { Suspense } from "react"
import { Loader2 } from "lucide-react"
import { ConnectCallback } from "./connect-callback"

/**
 * OAuth callback landing page.
 * Wraps the actual component in Suspense because useSearchParams()
 * requires it in Next.js 14+ for static generation.
 */
export default function ConnectPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen dot-grid-bg flex items-center justify-center">
          <Loader2 size={24} className="animate-spin text-muted-foreground" />
        </div>
      }
    >
      <ConnectCallback />
    </Suspense>
  )
}
