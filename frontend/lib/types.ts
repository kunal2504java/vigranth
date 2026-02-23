export type Platform = "gmail" | "slack" | "discord" | "telegram" | "whatsapp" | "outlook"

export type Priority = "urgent" | "action_needed" | "fyi" | "noise"

export type Sentiment = "positive" | "neutral" | "negative" | "tense" | "distressed"

export interface Contact {
  id: string
  name: string
  email?: string
  avatar?: string
  platform: Platform
  isVip: boolean
  relationship: string
  conversationCount: number
}

export interface Message {
  id: string
  platform: Platform
  sender: Contact
  subject?: string
  preview: string
  content: string
  threadId: string
  priority: Priority
  priorityScore: number
  priorityReason: string
  sentiment: Sentiment
  sentimentAdvice?: string
  aiContextNote: string
  receivedAt: Date
  isRead: boolean
  isDone: boolean
  snoozedUntil: Date | null
}

export interface ThreadMessage {
  id: string
  senderName: string
  isMe: boolean
  content: string
  sentAt: Date
  platform: Platform
}

export interface ThreadSummary {
  points: string[]
  tone: string
}

export interface Thread {
  id: string
  messages: ThreadMessage[]
  summary?: ThreadSummary
}

export interface PlatformConnection {
  platform: Platform
  isConnected: boolean
  isAvailable: boolean
  displayName: string
  description: string
  lastSynced?: Date
}

export interface User {
  id: string
  name: string
  email: string
  avatar?: string
}

export interface NotificationSettings {
  pushEnabled: boolean
  urgentOnly: boolean
  quietHoursStart: string
  quietHoursEnd: string
}
