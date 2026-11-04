export interface AuthUser {
  id: string
  email: string
  name: string
}

export interface AuthSession {
  access_token: string
  token_type: string
  user: AuthUser
  workspace_id: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ""
const TOKEN_KEY = "pbl6_access_token"
const USER_KEY = "pbl6_auth_user"
const listeners = new Set<() => void>()

function notify() {
  listeners.forEach((listener) => listener())
}

export function subscribeAuth(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function getAuthToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function getStoredUserRaw(): string {
  try {
    return localStorage.getItem(USER_KEY) ?? ""
  } catch {
    return ""
  }
}

export function getStoredUser(): AuthUser | null {
  const raw = getStoredUserRaw()
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}

export function authHeaders(): Record<string, string> {
  const token = getAuthToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function storeSession(session: AuthSession) {
  try {
    localStorage.setItem(TOKEN_KEY, session.access_token)
    localStorage.setItem(USER_KEY, JSON.stringify(session.user))
  } catch {
    // Bỏ qua khi trình duyệt chặn localStorage.
  }
  notify()
}

export function clearSession() {
  try {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  } catch {
    // Bỏ qua khi trình duyệt chặn localStorage.
  }
  notify()
}

async function parseError(response: Response): Promise<string> {
  const text = await response.text()
  try {
    const data = JSON.parse(text) as { detail?: unknown }
    if (typeof data.detail === "string") return data.detail
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : ""))
        .filter(Boolean)
        .join("; ")
    }
  } catch {
    // Không phải JSON.
  }
  if ([502, 503, 504].includes(response.status)) {
    return "Không kết nối được backend. Hãy khởi động backend bằng start_app.bat hoặc start_all.bat rồi thử lại."
  }
  return text || `HTTP ${response.status}`
}

export async function isBackendReachable(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/api/v1/status`)
    return response.ok
  } catch {
    return false
  }
}

async function authenticate(path: "/register" | "/login", email: string, password: string) {
  const response = await fetch(`${API_BASE}/api/v1/auth${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  })
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  const session = (await response.json()) as AuthSession
  storeSession(session)
  return session
}

export function login(email: string, password: string) {
  return authenticate("/login", email, password)
}

export function register(email: string, password: string) {
  return authenticate("/register", email, password)
}

export async function fetchCurrentSession(): Promise<AuthSession | null> {
  const token = getAuthToken()
  if (!token) return null
  const response = await fetch(`${API_BASE}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (response.status === 401) {
    clearSession()
    return null
  }
  if (!response.ok) {
    throw new Error(await parseError(response))
  }
  const data = (await response.json()) as {
    user: AuthUser
    workspace_id: string
  }
  const session: AuthSession = {
    access_token: token,
    token_type: "bearer",
    user: data.user,
    workspace_id: data.workspace_id,
  }
  storeSession(session)
  return session
}

export function googleLoginUrl(): string {
  return `${API_BASE}/api/v1/auth/google`
}

export async function isGoogleAuthEnabled(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/api/v1/status`)
    if (!response.ok) return false
    const data = (await response.json()) as { google_auth_enabled?: boolean }
    return Boolean(data.google_auth_enabled)
  } catch {
    return false
  }
}

export function logout() {
  clearSession()
}

/**
 * Google OAuth redirects về `/#access_token=...`. Đọc token, lưu lại và xoá hash.
 */
export function consumeOAuthTokenFromHash() {
  if (typeof window === "undefined") return
  const hash = window.location.hash.startsWith("#") ? window.location.hash.slice(1) : ""
  if (!hash.includes("access_token=")) return
  const params = new URLSearchParams(hash)
  const token = params.get("access_token")
  if (token) {
    try {
      localStorage.setItem(TOKEN_KEY, token)
    } catch {
      // Bỏ qua khi trình duyệt chặn localStorage.
    }
    notify()
  }
  window.history.replaceState(null, "", window.location.pathname + window.location.search)
}
