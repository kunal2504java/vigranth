/**
 * Typed API client for the UnifyInbox backend.
 * Base URL: http://localhost:8000
 * All authenticated requests require a Bearer token stored in localStorage.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

// ── Token storage ──────────────────────────────────────────────────────────

export function getToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem("access_token")
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem("access_token", access)
  localStorage.setItem("refresh_token", refresh)
}

export function clearTokens(): void {
  localStorage.removeItem("access_token")
  localStorage.removeItem("refresh_token")
}

// ── Base fetch wrapper ─────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  skipAuth = false
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  }

  if (!skipAuth) {
    const token = getToken()
    if (token) headers["Authorization"] = `Bearer ${token}`
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // ignore
    }
    throw new ApiError(res.status, detail)
  }

  // 204 No Content
  if (res.status === 204) return {} as T

  return res.json() as Promise<T>
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message)
    this.name = "ApiError"
  }
}

// ── Auth ───────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface UserResponse {
  id: string
  email: string
  name: string | null
  created_at: string | null
}

export const auth = {
  register(name: string, email: string, password: string) {
    return apiFetch<TokenResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    }, true)
  },

  login(email: string, password: string) {
    return apiFetch<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }, true)
  },

  me() {
    return apiFetch<UserResponse>("/auth/me")
  },

  refresh(refreshToken: string) {
    return apiFetch<TokenResponse>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: refreshToken }),
    }, true)
  },
}

// ── Feed ───────────────────────────────────────────────────────────────────

export interface ApiSender {
  id: string
  name: string
  email: string | null
  is_vip: boolean
}

export interface ApiAiEnrichment {
  priority_score: number
  priority_label: "urgent" | "action_needed" | "fyi" | "noise"
  sentiment: "positive" | "neutral" | "negative" | "tense" | "distressed"
  summary: string
  context_note: string
  suggested_actions: string[]
  is_complaint: boolean
  needs_careful_response: boolean
  suggested_approach: string
  classification_reasoning: string
}

export interface ApiMessage {
  id: string
  user_id: string
  platform: string
  platform_message_id: string
  thread_id: string
  sender: ApiSender
  content_text: string
  timestamp: string
  is_read: boolean
  is_done: boolean
  snoozed_until: string | null
  ai_enrichment: ApiAiEnrichment
  draft_reply: string | null
  created_at: string | null
}

export interface FeedResponse {
  messages: ApiMessage[]
  total: number
  has_more: boolean
}

export const feed = {
  get(params?: { limit?: number; offset?: number; platform?: string; priority?: string }) {
    const qs = new URLSearchParams()
    if (params?.limit) qs.set("limit", String(params.limit))
    if (params?.offset) qs.set("offset", String(params.offset))
    if (params?.platform) qs.set("platform", params.platform)
    if (params?.priority) qs.set("priority", params.priority)
    const query = qs.toString() ? `?${qs.toString()}` : ""
    return apiFetch<FeedResponse>(`/api/v1/feed${query}`)
  },

  getThread(platform: string, threadId: string) {
    return apiFetch<{ messages: ApiMessage[]; summary: unknown; message_count: number }>(
      `/api/v1/thread/${platform}/${threadId}`
    )
  },

  updateMessage(messageId: string, payload: {
    is_read?: boolean
    is_done?: boolean
    snoozed_until?: string
  }) {
    return apiFetch<{ success: boolean }>(`/api/v1/message/${messageId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    })
  },
}

// ── Actions ────────────────────────────────────────────────────────────────

export interface DraftResponse {
  message_id: string
  draft: string
  tone: string
}

export const actions = {
  generateDraft(messageId: string) {
    return apiFetch<DraftResponse>(`/api/v1/draft/${messageId}`, {
      method: "POST",
    })
  },

  saveDraft(messageId: string, draft: string) {
    return apiFetch<{ success: boolean }>(`/api/v1/draft/${messageId}`, {
      method: "PUT",
      body: JSON.stringify({ draft }),
    })
  },

  send(messageId: string, content: string) {
    return apiFetch<{ success: boolean; platform_message_id?: string }>(
      `/api/v1/send/${messageId}`,
      {
        method: "POST",
        body: JSON.stringify({ content }),
      }
    )
  },
}

// ── Platforms ──────────────────────────────────────────────────────────────

export interface PlatformStatus {
  platform: string
  connected: boolean
  last_sync: string | null
  platform_user_id: string | null
}

// ── Telegram Auth ─────────────────────────────────────────────────────────

export interface TelegramStartResponse {
  success: boolean
  phone_code_hash: string
  session: string
}

export interface TelegramVerifyResponse {
  success: boolean
  telegram_user_id: string
  username: string
  name: string
}

export const telegram = {
  /** Step 1: Send OTP to the user's phone number */
  sendCode(phone: string) {
    return apiFetch<TelegramStartResponse>("/api/v1/platforms/telegram/start", {
      method: "POST",
      body: JSON.stringify({ phone }),
    })
  },

  /** Step 2: Verify OTP code and store the Telethon session */
  verifyCode(phone: string, code: string, phoneCodeHash: string, session: string, password?: string) {
    return apiFetch<TelegramVerifyResponse>("/api/v1/platforms/telegram/verify", {
      method: "POST",
      body: JSON.stringify({
        phone,
        code,
        phone_code_hash: phoneCodeHash,
        session,
        password: password ?? "",
      }),
    })
  },
}

// ── OAuth Connect URLs ────────────────────────────────────────────────────

/**
 * Build the backend OAuth initiation URL for a platform.
 * The browser navigates to this URL, which redirects to the platform's
 * consent screen, then back to /connect on success.
 */
export function getOAuthConnectUrl(platform: "gmail" | "slack" | "discord"): string | null {
  const token = getToken()
  if (!token) return null
  return `${BASE_URL}/auth/${platform}/connect?token=${encodeURIComponent(token)}`
}

// ── Platforms ──────────────────────────────────────────────────────────────

export const platforms = {
  list() {
    return apiFetch<PlatformStatus[]>("/api/v1/platforms")
  },

  connect(platform: string, token: string) {
    return apiFetch<{ success: boolean; message: string }>(
      `/api/v1/platforms/${platform}/connect`,
      {
        method: "POST",
        body: JSON.stringify({ token }),
      }
    )
  },

  disconnect(platform: string) {
    return apiFetch<{ success: boolean; message: string }>(
      `/api/v1/platforms/${platform}`,
      { method: "DELETE" }
    )
  },
}
