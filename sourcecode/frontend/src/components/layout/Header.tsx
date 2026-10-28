import { useMemo } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"
import { ChevronRight, Menu, Moon, Palette, Settings, Sun } from "lucide-react"
import {
  Button,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  Tooltip,
} from "@/components/ui"
import { useAppStore } from "@/store/app-store"

interface Crumb {
  label: string
  to?: string
}

export function AppHeader() {
  const location = useLocation()
  const navigate = useNavigate()
  const setMobile = useAppStore((s) => s.setMobileNavOpen)
  const status = useAppStore((s) => s.status)
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const workspaces = useAppStore((s) => s.workspaces)
  const notebooks = useAppStore((s) => s.notebooks)
  const documents = useAppStore((s) => s.documents)
  const conversations = useAppStore((s) => s.conversations)

  const breadcrumbs = useMemo<Crumb[]>(() => {
    const { pathname } = location
    const segments = pathname.split("/").filter(Boolean)

    if (segments.length === 0 || segments[0] === "dashboard") {
      return [{ label: "Tổng quan" }]
    }
    if (segments[0] === "chat") {
      const conv = segments[1] ? conversations.find((c) => c.id === segments[1]) : undefined
      return conv
        ? [{ label: "Hỏi đáp AI", to: "/chat" }, { label: conv.title }]
        : [{ label: "Hỏi đáp AI" }]
    }
    if (segments[0] === "knowledge") {
      const ws = segments[1] ? workspaces.find((w) => w.id === segments[1]) : undefined
      const nb = segments[3] ? notebooks.find((n) => n.id === segments[3]) : undefined
      if (ws && segments[2] === "notebooks") {
        return [
          { label: "Kho tri thức", to: "/knowledge" },
          { label: ws.name, to: `/knowledge/${ws.id}?tab=notebooks` },
          { label: nb?.name ?? "Notebook" },
        ]
      }
      return ws
        ? [{ label: "Kho tri thức", to: "/knowledge" }, { label: ws.name }]
        : [{ label: "Kho tri thức" }]
    }
    if (segments[0] === "documents") {
      const doc = segments[1] ? documents.find((d) => d.id === segments[1]) : undefined
      return doc
        ? [{ label: "Tài liệu", to: "/documents" }, { label: doc.fileName }]
        : [{ label: "Tài liệu" }]
    }
    if (segments[0] === "study") {
      return [{ label: "Công cụ học tập" }]
    }
    if (segments[0] === "settings") {
      return [{ label: "Cài đặt" }]
    }
    if (segments[0] === "design-system") {
      return [{ label: "Design System" }]
    }
    return [{ label: segments.join(" / ") }]
  }, [location, workspaces, notebooks, documents, conversations])

  const isLiveBackend = status.backendOnline && !status.usingMock
  const statusTooltip = isLiveBackend
    ? "Đã kết nối máy chủ AI. Bấm để xem chi tiết."
    : "Đang chạy chế độ dữ liệu cục bộ trên trình duyệt. Bấm để xem chi tiết."

  return (
    <header className="flex h-11 shrink-0 items-center justify-between gap-3 border-b border-line bg-bg px-3 md:px-6">
      {/* Left: Mobile Menu + Breadcrumb */}
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0 md:hidden"
          aria-label="Mở menu điều hướng"
          onClick={() => setMobile(true)}
        >
          <Menu className="h-4 w-4" />
        </Button>

        <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-[13px]">
          {breadcrumbs.map((crumb, index) => {
            const isLast = index === breadcrumbs.length - 1
            return (
              <span key={`${crumb.label}-${index}`} className="flex min-w-0 items-center gap-1.5">
                {index > 0 ? <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted/60" /> : null}
                {crumb.to && !isLast ? (
                  <Link
                    to={crumb.to}
                    className="max-w-[160px] truncate text-muted transition-colors hover:text-ink"
                  >
                    {crumb.label}
                  </Link>
                ) : (
                  <span
                    className={
                      isLast
                        ? "max-w-[220px] truncate font-semibold text-ink sm:max-w-[340px]"
                        : "max-w-[160px] truncate text-muted"
                    }
                  >
                    {crumb.label}
                  </span>
                )}
              </span>
            )
          })}
        </nav>
      </div>

      {/* Right: Trạng thái gọn (chi tiết hiện khi hover), Theme Toggle, User Menu */}
      <div className="flex shrink-0 items-center gap-1">
        <Tooltip content={statusTooltip} side="bottom">
          <button
            type="button"
            onClick={() => navigate("/settings?section=status")}
            aria-label={statusTooltip}
            className="inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-xs text-muted transition-colors hover:bg-bg-hover hover:text-ink"
          >
            <span
              className={`h-2 w-2 rounded-full ${
                isLiveBackend ? "bg-success" : "bg-muted/70"
              }`}
            />
            <span className="hidden sm:inline">
              {isLiveBackend ? "Trực tuyến" : "Cục bộ"}
            </span>
          </button>
        </Tooltip>

        <Tooltip
          content={theme === "light" ? "Chuyển sang giao diện tối" : "Chuyển sang giao diện sáng"}
          side="bottom"
        >
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            aria-label={theme === "light" ? "Bật chế độ tối" : "Bật chế độ sáng"}
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          >
            {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
          </Button>
        </Tooltip>

        <DropdownMenu
          trigger={
            <button
              type="button"
              className="ml-0.5 flex h-6 w-6 items-center justify-center rounded-full border border-line bg-bg-secondary text-[11px] font-medium text-ink transition-colors hover:bg-bg-hover"
              aria-label="Tài khoản và cài đặt"
            >
              TV
            </button>
          }
        >
          <DropdownMenuLabel>Không gian cá nhân</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            icon={<Settings className="h-3.5 w-3.5" />}
            onClick={() => navigate("/settings")}
          >
            Cài đặt
          </DropdownMenuItem>
          <DropdownMenuItem
            icon={<Palette className="h-3.5 w-3.5" />}
            onClick={() => navigate("/design-system")}
          >
            Giao diện & Thiết kế
          </DropdownMenuItem>
          <DropdownMenuItem
            icon={theme === "light" ? <Moon className="h-3.5 w-3.5" /> : <Sun className="h-3.5 w-3.5" />}
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          >
            {theme === "light" ? "Chế độ tối" : "Chế độ sáng"}
          </DropdownMenuItem>
        </DropdownMenu>
      </div>
    </header>
  )
}
