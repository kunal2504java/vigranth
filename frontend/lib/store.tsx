"use client"

import {
  createContext,
  useContext,
  useState,
  useCallback,
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

// ── Types ───────────────────────────────────────────────

type ActiveFilter = "all" | "urgent" | "action_needed" | "fyi" | "snoozed" | Platform

interface StoreValue {
  // Auth
  user: User | null
  login: (email: string, password: string) => void
  register: (name: string, email: string, password: string) => void
  googleAuth: () => void
  logout: () => void

  // Platforms
  platforms: PlatformConnection[]
  connectPlatform: (platform: Platform) => void
  disconnectPlatform: (platform: Platform) => void
  connectedCount: number

  // Messages
  messages: Message[]
  selectedMessageId: string | null
  selectMessage: (id: string | null) => void
  markDone: (id: string) => void
  snoozeMessage: (id: string, until: Date) => void
  unsnooze: (id: string) => void

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

// ── Provider ────────────────────────────────────────────

export function StoreProvider({ children }: { children: ReactNode }) {
  // Auth
  const [user, setUser] = useState<User | null>(null)

  const login = useCallback((_email: string, _password: string) => {
    setUser({
      id: "u1",
      name: "Alex Johnson",
      email: _email,
    })
  }, [])

  const register = useCallback((name: string, email: string, _password: string) => {
    setUser({ id: "u1", name, email })
  }, [])

  const googleAuth = useCallback(() => {
    setUser({
      id: "u1",
      name: "Alex Johnson",
      email: "alex@example.com",
    })
  }, [])

  const logout = useCallback(() => {
    setUser(null)
  }, [])

  // Platforms
  const [platforms, setPlatforms] = useState<PlatformConnection[]>(
    PLATFORM_CONNECTIONS.map((p) => ({ ...p }))
  )

  const connectPlatform = useCallback((platform: Platform) => {
    setPlatforms((prev) =>
      prev.map((p) =>
        p.platform === platform
          ? { ...p, isConnected: true, lastSynced: new Date() }
          : p
      )
    )
  }, [])

  const disconnectPlatform = useCallback((platform: Platform) => {
    setPlatforms((prev) =>
      prev.map((p) =>
        p.platform === platform
          ? { ...p, isConnected: false, lastSynced: undefined }
          : p
      )
    )
  }, [])

  const connectedCount = platforms.filter((p) => p.isConnected).length

  // Messages
  const [messages, setMessages] = useState<Message[]>(
    MOCK_MESSAGES.map((m) => ({ ...m }))
  )
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null)

  const selectMessage = useCallback((id: string | null) => {
    setSelectedMessageId(id)
    if (id) {
      setMessages((prev) =>
        prev.map((m) => (m.id === id ? { ...m, isRead: true } : m))
      )
    }
  }, [])

  const markDone = useCallback((id: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, isDone: true } : m))
    )
    setSelectedMessageId((prev) => (prev === id ? null : prev))
  }, [])

  const snoozeMessage = useCallback((id: string, until: Date) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, snoozedUntil: until } : m))
    )
    setSelectedMessageId((prev) => (prev === id ? null : prev))
  }, [])

  const unsnooze = useCallback((id: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, snoozedUntil: null } : m))
    )
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
  const triggerSync = useCallback(() => setLastSynced(new Date()), [])

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
        login,
        register,
        googleAuth,
        logout,
        platforms,
        connectPlatform,
        disconnectPlatform,
        connectedCount,
        messages,
        selectedMessageId,
        selectMessage,
        markDone,
        snoozeMessage,
        unsnooze,
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
