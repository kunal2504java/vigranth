"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useStore } from "@/lib/store"
import { getToken } from "@/lib/api"

/**
 * Redirects to /auth if the user is not logged in.
 * Returns { ready: boolean } — render nothing until ready is true
 * to prevent flash of protected content.
 */
export function useAuthGuard(): { ready: boolean } {
  const router = useRouter()
  const { user } = useStore()

  useEffect(() => {
    // If there's no token at all, redirect immediately
    const token = getToken()
    if (!token) {
      router.replace("/auth")
    }
  }, [router])

  // user is populated asynchronously from /auth/me on mount
  // token presence is the fast check; user object confirms it's valid
  const hasToken = typeof window !== "undefined" && !!getToken()

  return { ready: hasToken && !!user }
}
