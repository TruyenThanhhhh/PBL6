import { useEffect } from "react"
import { Outlet } from "react-router-dom"
import { AppSidebar } from "./Sidebar"
import { AppHeader } from "./Header"
import { Toasts } from "@/components/common/Toasts"
import { ConnectionBanner } from "@/components/common/ConnectionBanner"
import { GlobalSearch } from "@/features/search/GlobalSearch"
import { useAppStore } from "@/store/app-store"
import { useSystemStatus } from "@/hooks/useSystemStatus"

export function AppShell() {
  const theme = useAppStore((s) => s.theme)
  useSystemStatus()

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark")
  }, [theme])

  return (
    <div className="motivo-canvas flex h-screen w-full overflow-hidden text-ink">
      <AppSidebar />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <AppHeader />
        <ConnectionBanner />
        <main id="main-content" className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
      <Toasts />
      <GlobalSearch />
    </div>
  )
}
