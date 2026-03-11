"use client"

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react"
import type {
  User,
  Message,
  Platform,
  Contact,
  NotificationSettings,
  PlatformConnection,
} from "./types"
import {
  MOCK_MESSAGES,
  MOCK_VIP_CONTACTS,
  PLATFORM_CONNECTIONS,
} from "./mock-data"
import {
  auth as apiAuth,
  feed as apiFeed,
  platforms as apiPlatforms,
  actions as apiActions,
  setTokens,
  clearTokens,
  getToken,
  type ApiMessage,
} from "./api"

// ── Types ───────────────────────────────────────────────

type ActiveFilter = "all" | "urgent" | "action_needed" | "fyi" | "snoozed" | Platform

interface StoreValue {
  // Auth
  user: User | null
  isAuthLoading: boolean
  authError: string | null
  login: (email: string, password: string) => Promise<void>
  register: (name: string, email: string, password: string) => Promise<void>
  googleAuth: () => void
  logout: () => void

  // Platforms
  platforms: PlatformConnection[]
  connectPlatform: (platform: Platform) => void
  disconnectPlatform: (platform: Platform) => void
  connectedCount: number

  // Messages
  messages: Message[]
  isMessagesLoading: boolean
  selectedMessageId: string | null
  selectMessage: (id: string | null) => void
  markDone: (id: string) => void
  snoozeMessage: (id: string, until: Date) => void
  unsnooze: (id: string) => void
  generateDraft: (id: string) => Promise<string>

  // VIP
  vipContacts: Contact[]
  addVip: (contact: Contact) => void
  removeVip: (contactId: string) => void

  // Notifications
  notificationSettings: NotificationSettings
  updateNotificationSettings: (s: Partial<NotificationSettings>) => void

  // Feed
  activeFilter: ActiveFilter
  setActiveFilter: (f: ActiveFilter) => void

  // Search
  searchQuery: string
  setSearchQuery: (q: string) => void

  // Sync
  lastSynced: Date | null
  triggerSync: () => void

  // Counts
  urgentCount: number
  actionCount: number
  fyiCount: number
  snoozedCount: number
  totalUnread: number
}

const StoreContext = createContext<StoreValue | null>(null)

// ── Helpers ──────────────────────────────────────────────

/** Map an API message to the frontend Message type */
function apiMsgToMessage(m: ApiMessage): Message {
  const platformMap: Record<string, Platform> = {
    gmail: "gmail",
    slack: "slack",
    telegram: "telegram",
    discord: "discord",
    whatsapp: "whatsapp",
    outlook: "outlook",
  }
  const priorityMap: Record<string, Message["priority"]> = {
    urgent: "urgent",
    action_needed: "action_needed",
    fyi: "fyi",
    noise: "noise",
  }
  const sentimentMap: Record<string, Message["sentiment"]> = {
    positive: "positive",
    neutral: "neutral",
    negative: "negative",
    tense: "tense",
    distressed: "distressed",
  }

  return {
    id: m.id,
    platform: platformMap[m.platform] ?? "gmail",
    sender: {
      id: m.sender.id,
      name: m.sender.name,
      email: m.sender.email ?? undefined,
      platform: platformMap[m.platform] ?? "gmail",
      isVip: m.sender.is_vip ?? false,
      relationship: "contact",
      conversationCount: 0,
    },
    subject: undefined,
    preview: m.content_text.slice(0, 140),
    content: m.content_text,
    threadId: m.thread_id,
    priority: priorityMap[m.ai_enrichment.priority_label] ?? "fyi",
    priorityScore: m.ai_enrichment.priority_score,
    priorityReason: m.ai_enrichment.classification_reasoning,
    sentiment: sentimentMap[m.ai_enrichment.sentiment] ?? "neutral",
    sentimentAdvice: m.ai_enrichment.suggested_approach || undefined,
    aiContextNote: m.ai_enrichment.context_note,
    receivedAt: new Date(m.timestamp),
    isRead: m.is_read,
    isDone: m.is_done,
    snoozedUntil: m.snoozed_until ? new Date(m.snoozed_until) : null,
  }
}

// ── Provider ────────────────────────────────────────────

export function StoreProvider({ children }: { children: ReactNode }) {
  // Auth
  const [user, setUser] = useState<User | null>(null)
  const [isAuthLoading, setIsAuthLoading] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)

  // Rehydrate user from token on mount
  useEffect(() => {
    const token = getToken()
    if (token) {
      apiAuth.me()
        .then((u) => setUser({ id: u.id, name: u.name ?? u.email, email: u.email }))
        .catch(() => clearTokens())
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    setIsAuthLoading(true)
    setAuthError(null)
    try {
      const res = await apiAuth.login(email, password)
      setTokens(res.access_token, res.refresh_token)
      const me = await apiAuth.me()
      setUser({ id: me.id, name: me.name ?? me.email, email: me.email })
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Login failed"
      setAuthError(msg)
      throw err
    } finally {
      setIsAuthLoading(false)
    }
  }, [])

  const register = useCallback(async (name: string, email: string, password: string) => {
    setIsAuthLoading(true)
    setAuthError(null)
    try {
      const res = await apiAuth.register(name, email, password)
      setTokens(res.access_token, res.refresh_token)
      setUser({ id: "pending", name, email })
      // Fetch real user id
      const me = await apiAuth.me()
      setUser({ id: me.id, name: me.name ?? name, email: me.email })
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Registration failed"
      setAuthError(msg)
      throw err
    } finally {
      setIsAuthLoading(false)
    }
  }, [])

  const googleAuth = useCallback(() => {
    // Google OAuth is a server-side redirect flow — stub for now
    setUser({
      id: "u1",
      name: "Alex Johnson",
      email: "alex@example.com",
    })
  }, [])

  const logout = useCallback(() => {
    clearTokens()
    setUser(null)
    setMessages(MOCK_MESSAGES.map((m) => ({ ...m })))
  }, [])

  // Platforms
  const [platformConnections, setPlatformConnections] = useState<PlatformConnection[]>(
    PLATFORM_CONNECTIONS.map((p) => ({ ...p }))
  )

  // Sync platform status from API when user is present
  useEffect(() => {
    if (!user) return
    apiPlatforms.list()
      .then((apiList) => {
        setPlatformConnections((prev) =>
          prev.map((p) => {
            const found = apiList.find((a) => a.platform === p.platform)
            if (!found) return p
            return {
              ...p,
              isConnected: found.connected,
              lastSynced: found.last_sync ? new Date(found.last_sync) : undefined,
            }
          })
        )
      })
      .catch(() => {
        // keep mock state on error
      })
  }, [user])

  const connectPlatform = useCallback((platform: Platform) => {
    setPlatformConnections((prev) =>
      prev.map((p) =>
        p.platform === platform
          ? { ...p, isConnected: true, lastSynced: new Date() }
          : p
      )
    )
  }, [])

  const disconnectPlatform = useCallback((platform: Platform) => {
    // Fire-and-forget API call
    apiPlatforms.disconnect(platform).catch(() => {})
    setPlatformConnections((prev) =>
      prev.map((p) =>
        p.platform === platform
          ? { ...p, isConnected: false, lastSynced: undefined }
          : p
      )
    )
  }, [])

  const connectedCount = platformConnections.filter((p) => p.isConnected).length

  // Messages
  const [messages, setMessages] = useState<Message[]>(
    MOCK_MESSAGES.map((m) => ({ ...m }))
  )
  const [isMessagesLoading, setIsMessagesLoading] = useState(false)
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null)

  // Fetch real messages when user is present
  useEffect(() => {
    if (!user) return
    setIsMessagesLoading(true)
    apiFeed.get({ limit: 100 })
      .then((res) => {
        if (res.messages.length > 0) {
          setMessages(res.messages.map(apiMsgToMessage))
        }
        // If API has no messages, keep mock data for demo purposes
      })
      .catch(() => {
        // keep mock data on error
      })
      .finally(() => setIsMessagesLoading(false))
  }, [user])

  const selectMessage = useCallback((id: string | null) => {
    setSelectedMessageId(id)
    if (id) {
      setMessages((prev) =>
        prev.map((m) => (m.id === id ? { ...m, isRead: true } : m))
      )
      // Mark read on backend (fire-and-forget)
      apiFeed.updateMessage(id, { is_read: true }).catch(() => {})
    }
  }, [])

  const markDone = useCallback((id: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, isDone: true } : m))
    )
    setSelectedMessageId((prev) => (prev === id ? null : prev))
    // Persist on backend
    apiFeed.updateMessage(id, { is_done: true }).catch(() => {})
  }, [])

  const snoozeMessage = useCallback((id: string, until: Date) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, snoozedUntil: until } : m))
    )
    setSelectedMessageId((prev) => (prev === id ? null : prev))
    apiFeed.updateMessage(id, { snoozed_until: until.toISOString() }).catch(() => {})
  }, [])

  const unsnooze = useCallback((id: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, snoozedUntil: null } : m))
    )
  }, [])

  const generateDraft = useCallback(async (id: string): Promise<string> => {
    const res = await apiActions.generateDraft(id)
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, draftReply: res.draft } : m))
    )
    return res.draft
  }, [])

  // VIP
  const [vipContacts, setVipContacts] = useState<Contact[]>([...MOCK_VIP_CONTACTS])

  const addVip = useCallback((contact: Contact) => {
    setVipContacts((prev) => {
      if (prev.find((c) => c.id === contact.id)) return prev
      return [...prev, { ...contact, isVip: true }]
    })
  }, [])

  const removeVip = useCallback((contactId: string) => {
    setVipContacts((prev) => prev.filter((c) => c.id !== contactId))
  }, [])

  // Notifications
  const [notificationSettings, setNotificationSettings] =
    useState<NotificationSettings>({
      pushEnabled: true,
      urgentOnly: false,
      quietHoursStart: "22:00",
      quietHoursEnd: "08:00",
    })

  const updateNotificationSettings = useCallback(
    (s: Partial<NotificationSettings>) => {
      setNotificationSettings((prev) => ({ ...prev, ...s }))
    },
    []
  )

  // Feed
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>("all")
  const [searchQuery, setSearchQuery] = useState("")

  // Sync
  const [lastSynced, setLastSynced] = useState<Date | null>(new Date())
  const triggerSync = useCallback(() => {
    setLastSynced(new Date())
    if (!user) return
    setIsMessagesLoading(true)
    apiFeed.get({ limit: 100 })
      .then((res) => {
        if (res.messages.length > 0) {
          setMessages(res.messages.map(apiMsgToMessage))
        }
      })
      .catch(() => {})
      .finally(() => setIsMessagesLoading(false))
  }, [user])

  // Computed counts (active messages only — not done, not snoozed)
  const active = messages.filter((m) => !m.isDone && !m.snoozedUntil)
  const urgentCount = active.filter((m) => m.priority === "urgent").length
  const actionCount = active.filter((m) => m.priority === "action_needed").length
  const fyiCount = active.filter((m) => m.priority === "fyi" || m.priority === "noise").length
  const snoozedCount = messages.filter((m) => !m.isDone && m.snoozedUntil).length
  const totalUnread = active.filter((m) => !m.isRead).length

  return (
    <StoreContext.Provider
      value={{
        user,
        isAuthLoading,
        authError,
        login,
        register,
        googleAuth,
        logout,
        platforms: platformConnections,
        connectPlatform,
        disconnectPlatform,
        connectedCount,
        messages,
        isMessagesLoading,
        selectedMessageId,
        selectMessage,
        markDone,
        snoozeMessage,
        unsnooze,
        generateDraft,
        vipContacts,
        addVip,
        removeVip,
        notificationSettings,
        updateNotificationSettings,
        activeFilter,
        setActiveFilter,
        searchQuery,
        setSearchQuery,
        lastSynced,
        triggerSync,
        urgentCount,
        actionCount,
        fyiCount,
        snoozedCount,
        totalUnread,
      }}
    >
      {children}
    </StoreContext.Provider>
  )
}

// ── Hook ────────────────────────────────────────────────

export function useStore(): StoreValue {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error("useStore must be used within StoreProvider")
  return ctx
}
