import { useMemo, useSyncExternalStore } from "react"
import type { AuthUser } from "@/services/auth-service"
import { getAuthToken, getStoredUserRaw, subscribeAuth } from "@/services/auth-service"

export function useAuthSession() {
  const token = useSyncExternalStore(subscribeAuth, getAuthToken, () => null)
  const userJson = useSyncExternalStore(subscribeAuth, getStoredUserRaw, () => "")
  const user = useMemo<AuthUser | null>(() => {
    if (!userJson) return null
    try {
      return JSON.parse(userJson) as AuthUser
    } catch {
      return null
    }
  }, [userJson])
  return { token, user, authenticated: Boolean(token) }
}
