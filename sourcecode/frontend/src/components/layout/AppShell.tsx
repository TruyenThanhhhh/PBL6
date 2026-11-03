import { useEffect } from "react"
import { Outlet } from "react-router-dom"
import { AppSidebar } from "./Sidebar"
import { AppHeader } from "./Header"
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
    <div className="flex h-screen w-full flex-col overflow-hidden bg-[#F7FAF9] text-ink">
      <AppHeader />
      <ConnectionBanner />
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <AppSidebar />
        <main id="main-content" className="min-h-0 min-w-0 flex-1 overflow-y-auto bg-white">
          <Outlet />
        </main>
      </div>
      <GlobalSearch />
    </div>
  )
}
