import { useEffect, useState } from "react"
import { NavLink, useLocation, useNavigate } from "react-router-dom"
import {
  BookOpen,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  FileUp,
  FolderOpen,
  FolderPlus,
  GraduationCap,
  Home,
  Layers,
  MessageSquare,
  Plus,
  Search,
  Settings,
  X,
} from "lucide-react"
import { useAppStore } from "@/store/app-store"
import {
  Button,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  Tooltip,
} from "@/components/ui"
import { NameDialog } from "@/components/common/NameDialog"
import { cn } from "@/utils/cn"

const NAV_ITEMS = [
  { to: "/dashboard", matchPaths: ["/", "/dashboard"], label: "Trang chủ", icon: Home },
  { to: "/chat", matchPaths: ["/chat"], label: "Hỏi đáp AI", icon: MessageSquare },
  { to: "/knowledge", matchPaths: ["/knowledge"], label: "Kho tri thức", icon: FolderOpen },
  { to: "/documents", matchPaths: ["/documents"], label: "Tài liệu", icon: BookOpen },
  { to: "/study", matchPaths: ["/study"], label: "Học tập", icon: GraduationCap },
  { to: "/settings", matchPaths: ["/settings"], label: "Cài đặt", icon: Settings },
]

function MotivoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={cn("h-5 w-5 text-brand", className)}
      aria-hidden="true"
    >
      <path
        d="M12 2.5v19M3.8 7.25l16.4 9.5M20.2 7.25l-16.4 9.5"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function AppSidebar() {
  const collapsed = useAppStore((s) => s.sidebarCollapsed)
  const toggle = useAppStore((s) => s.toggleSidebar)
  const mobile = useAppStore((s) => s.mobileNavOpen)
  const setMobile = useAppStore((s) => s.setMobileNavOpen)
  const workspaces = useAppStore((s) => s.workspaces)
  const notebooks = useAppStore((s) => s.notebooks)
  const documents = useAppStore((s) => s.documents)
  const conversations = useAppStore((s) => s.conversations)
  const current = useAppStore((s) => s.currentWorkspaceId)
  const setCurrent = useAppStore((s) => s.setCurrentWorkspace)
  const createConversation = useAppStore((s) => s.createConversation)
  const createWorkspace = useAppStore((s) => s.createWorkspace)
  const createNotebook = useAppStore((s) => s.createNotebook)
  const toast = useAppStore((s) => s.toast)

  const navigate = useNavigate()
  const location = useLocation()
  const [wsOpen, setWsOpen] = useState(false)
  const [nbOpen, setNbOpen] = useState(false)
  const [notebooksExpanded, setNotebooksExpanded] = useState(true)

  useEffect(() => {
    if (!mobile) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobile(false)
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [mobile, setMobile])

  const currentWs = workspaces.find((w) => w.id === current) ?? workspaces[0]
  const currentNotebooks = notebooks.filter((n) => n.workspaceId === currentWs?.id)
  const currentDocCount = documents.filter((d) => d.workspaceId === currentWs?.id).length

  const isRouteActive = (matchPaths: string[]) => {
    const { pathname } = location
    return matchPaths.some((p) =>
      p === "/" ? pathname === "/" : pathname === p || pathname.startsWith(`${p}/`),
    )
  }

  const handleNewChat = () => {
    const targetWs = currentWs?.id ?? "ws_research"
    const conv = createConversation(targetWs)
    navigate(`/chat/${conv.id}`)
    setMobile(false)
  }

  const handleOpenSearch = () => {
    setMobile(false)
    window.dispatchEvent(new Event("open-search"))
  }

  return (
    <>
      {mobile ? (
        <button
          type="button"
          className="fixed inset-0 z-30 bg-ink/30 md:hidden"
          aria-label="Đóng menu điều hướng"
          onClick={() => setMobile(false)}
        />
      ) : null}

      <aside
        aria-label="Thanh điều hướng chính"
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex h-full shrink-0 flex-col border-r border-line bg-bg-sidebar text-[13px] transition-[width,transform] duration-150 md:static md:translate-x-0",
          collapsed ? "w-[244px] md:w-[64px]" : "w-[244px]",
          mobile ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        {/* 1. Brand Logo + Workspace Switcher kiểu Motivo */}
        <div
          className={cn(
            "flex h-16 shrink-0 items-center justify-between gap-1.5 px-3 pt-2 pb-1",
            collapsed && "md:h-14 md:justify-center md:px-2",
          )}
        >
          {collapsed ? (
            <Tooltip content="Mở rộng thanh điều hướng" side="right">
              <button
                type="button"
                onClick={toggle}
                className="hidden h-9 w-9 items-center justify-center rounded-xl bg-brand-soft text-brand transition-colors hover:bg-bg-active md:flex"
                aria-label="Mở rộng sidebar"
              >
                <MotivoMark className="h-5 w-5" />
              </button>
            </Tooltip>
          ) : null}

          <div className={cn("min-w-0 flex-1", collapsed && "md:hidden")}>
            <DropdownMenu
              align="start"
              fullWidth
              className="w-[264px] rounded-2xl border border-line/80 bg-bg p-1.5 shadow-xl shadow-ink/5"
              trigger={
                <button
                  type="button"
                  className="group flex w-full items-center gap-2.5 rounded-xl border border-line/70 bg-bg-secondary/50 p-1.5 pr-2 text-left transition-all hover:border-brand/40 hover:bg-bg-hover hover:shadow-2xs focus:outline-hidden"
                  aria-label="Chuyển đổi không gian làm việc"
                >
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand shadow-2xs border border-brand/20 transition-transform group-hover:scale-105">
                    <MotivoMark className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1">
                      <span className="truncate text-xs font-bold text-ink transition-colors group-hover:text-brand">
                        {currentWs?.name ?? "Không gian mặc định"}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 text-[10px] text-muted">
                      <span className="truncate">knowledge.ai</span>
                      <span className="text-muted/40">·</span>
                      <span className="shrink-0 font-medium text-brand">
                        {currentDocCount} doc
                      </span>
                    </div>
                  </div>
                  <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted/60 transition-colors group-hover:text-ink" />
                </button>
              }
            >
              {/* Header */}
              <div className="mb-1 flex items-center justify-between border-b border-line/60 px-2.5 py-2">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-ink">
                  <FolderOpen className="h-3.5 w-3.5 text-brand" />
                  <span>Không gian làm việc</span>
                </div>
                <span className="rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-bold text-brand">
                  {workspaces.length} không gian
                </span>
              </div>

              {/* List Workspaces */}
              <div className="max-h-60 space-y-0.5 overflow-y-auto pr-0.5">
                {workspaces.map((w) => {
                  const docCount = documents.filter((d) => d.workspaceId === w.id).length
                  const chatCount = conversations.filter((c) => c.workspaceId === w.id).length
                  const isSelected = w.id === currentWs?.id
                  return (
                    <DropdownMenuItem
                      key={w.id}
                      onClick={() => {
                        setCurrent(w.id)
                        setMobile(false)
                        toast({
                          title: "Đã chuyển không gian làm việc",
                          description: `Đang làm việc trên: ${w.name}`,
                          tone: "info",
                        })
                        if (
                          location.pathname.startsWith("/knowledge/") &&
                          location.pathname !== "/knowledge"
                        ) {
                          navigate(`/knowledge/${w.id}`)
                        } else if (location.pathname.startsWith("/chat/")) {
                          const convInNewWs = conversations.find((c) => c.workspaceId === w.id)
                          navigate(convInNewWs ? `/chat/${convInNewWs.id}` : "/chat")
                        }
                      }}
                      className={cn(
                        "flex w-full items-center justify-between gap-2.5 rounded-xl px-2.5 py-2 text-left transition-all",
                        isSelected
                          ? "border border-brand/20 bg-brand-soft/70 font-medium"
                          : "border border-transparent hover:bg-bg-hover",
                      )}
                    >
                      <div className="flex min-w-0 flex-1 items-center gap-2.5">
                        <span
                          className={cn(
                            "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-bold shadow-2xs transition-colors",
                            isSelected
                              ? "bg-brand text-brand-fg"
                              : "bg-bg-secondary text-muted group-hover:text-ink",
                          )}
                        >
                          {w.name.charAt(0).toUpperCase()}
                        </span>

                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <span
                              className={cn(
                                "truncate text-xs",
                                isSelected ? "font-bold text-brand" : "font-semibold text-ink",
                              )}
                            >
                              {w.name}
                            </span>
                            {isSelected ? (
                              <span className="rounded bg-brand/15 px-1.5 py-0.2 text-[9px] font-bold text-brand">
                                Đang chọn
                              </span>
                            ) : null}
                          </div>
                          <p className="mt-0.5 truncate text-[10px] text-muted">
                            {docCount} tài liệu · {chatCount} hội thoại
                          </p>
                        </div>
                      </div>

                      {isSelected ? (
                        <Check className="h-4 w-4 shrink-0 stroke-[2.5] text-brand" />
                      ) : null}
                    </DropdownMenuItem>
                  )
                })}
              </div>

              <DropdownMenuSeparator />

              {/* Actions */}
              <DropdownMenuItem
                icon={<Plus className="h-3.5 w-3.5 text-brand" />}
                onClick={() => setWsOpen(true)}
                className="rounded-xl px-2.5 py-1.5 text-xs font-semibold text-brand hover:bg-brand-soft"
              >
                Tạo không gian mới...
              </DropdownMenuItem>

              <DropdownMenuItem
                icon={<Layers className="h-3.5 w-3.5 text-muted" />}
                onClick={() => {
                  navigate("/knowledge")
                  setMobile(false)
                }}
                className="rounded-xl px-2.5 py-1.5 text-xs text-muted hover:text-ink"
              >
                Quản lý tất cả không gian
              </DropdownMenuItem>
            </DropdownMenu>
          </div>

          {!collapsed ? (
            <Tooltip content="Thu gọn thanh bên" side="bottom">
              <Button
                variant="ghost"
                size="icon"
                className="hidden h-7 w-7 shrink-0 text-muted md:inline-flex"
                onClick={toggle}
                aria-label="Thu gọn sidebar"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
            </Tooltip>
          ) : null}

          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0 text-muted md:hidden"
            onClick={() => setMobile(false)}
            aria-label="Đóng menu"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* 2. Thao tác nhanh: Tìm kiếm & Tạo mới */}
        <div className="shrink-0 px-3 pt-2 pb-1">
          {collapsed ? (
            <div className="space-y-1">
              <Tooltip content="Tìm kiếm nhanh (Ctrl+K)" side="right">
                <button
                  type="button"
                  onClick={handleOpenSearch}
                  className="flex w-full items-center justify-center rounded-xl p-2 text-muted transition-colors hover:bg-bg-hover hover:text-ink"
                  aria-label="Tìm kiếm"
                >
                  <Search className="h-4 w-4" />
                </button>
              </Tooltip>
              <Tooltip content="Tạo mới" side="right">
                <button
                  type="button"
                  onClick={handleNewChat}
                  className="flex w-full items-center justify-center rounded-xl p-2 text-muted transition-colors hover:bg-bg-hover hover:text-ink"
                  aria-label="Tạo mới"
                >
                  <Plus className="h-4 w-4" />
                </button>
              </Tooltip>
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={handleOpenSearch}
                className="flex h-8 flex-1 items-center gap-2 rounded-xl border border-line bg-bg-secondary/70 px-3 text-left text-xs text-muted transition-colors hover:border-brand/40 hover:text-ink"
              >
                <Search className="h-3.5 w-3.5 shrink-0 text-brand" />
                <span className="flex-1 truncate">Tìm nhanh...</span>
                <kbd className="text-[10px] text-muted/80">⌘K</kbd>
              </button>

              <DropdownMenu
                align="start"
                trigger={
                  <span>
                    <Tooltip content="Tạo mới nhanh" side="bottom">
                      <button
                        type="button"
                        className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-primary-fg shadow-xs transition-opacity hover:opacity-90"
                        aria-label="Tạo mới"
                      >
                        <Plus className="h-4 w-4" />
                      </button>
                    </Tooltip>
                  </span>
                }
              >
                <DropdownMenuLabel>Tạo nhanh</DropdownMenuLabel>
                <DropdownMenuItem
                  icon={<MessageSquare className="h-3.5 w-3.5" />}
                  onClick={handleNewChat}
                >
                  Cuộc trò chuyện AI
                </DropdownMenuItem>
                <DropdownMenuItem
                  icon={<FileUp className="h-3.5 w-3.5" />}
                  onClick={() => {
                    navigate("/documents")
                    setMobile(false)
                  }}
                >
                  Tải lên tài liệu
                </DropdownMenuItem>
                <DropdownMenuItem
                  icon={<BookOpen className="h-3.5 w-3.5" />}
                  onClick={() => setNbOpen(true)}
                >
                  Notebook mới
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  icon={<FolderPlus className="h-3.5 w-3.5" />}
                  onClick={() => setWsOpen(true)}
                >
                  Không gian mới
                </DropdownMenuItem>
              </DropdownMenu>
            </div>
          )}
        </div>

        {/* 3. Navigation chính kiểu Motivo (Pill mint sáng + dấu › khi đang chọn) */}
        <nav className="mt-2 flex shrink-0 flex-col gap-1 px-3" aria-label="Menu chức năng">
          {NAV_ITEMS.map((item) => {
            const active = isRouteActive(item.matchPaths)
            const linkNode = (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setMobile(false)}
                className={cn(
                  "flex items-center gap-3 rounded-xl px-3 py-2 text-[13px] transition-all",
                  active
                    ? "bg-bg-active font-semibold text-ink shadow-[0_1px_2px_rgba(15,45,40,0.04)]"
                    : "text-muted hover:bg-bg-hover hover:text-ink",
                  collapsed && "md:justify-center md:px-2",
                )}
              >
                <item.icon
                  className={cn(
                    "h-4 w-4 shrink-0 transition-colors",
                    active ? "text-brand" : "text-muted",
                  )}
                />
                <span className={cn("flex-1 truncate", collapsed && "md:hidden")}>
                  {item.label}
                </span>
                {active && !collapsed ? (
                  <ChevronRight className="h-3.5 w-3.5 shrink-0 text-brand" />
                ) : null}
              </NavLink>
            )

            return collapsed ? (
              <Tooltip key={item.to} content={item.label} side="right">
                {linkNode}
              </Tooltip>
            ) : (
              linkNode
            )
          })}
        </nav>

        {/* 4. Khu vực Notebook thu gọn */}
        <div className={cn("mt-4 flex-1 overflow-y-auto px-3 pb-2", collapsed && "md:hidden")}>
          <div>
            <div className="group flex items-center justify-between rounded-lg px-2 py-1 text-[11px] font-semibold text-muted hover:bg-bg-hover">
              <button
                type="button"
                onClick={() => setNotebooksExpanded((v) => !v)}
                className="flex flex-1 items-center gap-1.5 text-left"
              >
                {notebooksExpanded ? (
                  <ChevronDown className="h-3 w-3 shrink-0" />
                ) : (
                  <ChevronRight className="h-3 w-3 shrink-0" />
                )}
                <span className="truncate uppercase tracking-wider">Notebook</span>
              </button>
              <Tooltip content="Thêm notebook" side="right">
                <button
                  type="button"
                  onClick={() => setNbOpen(true)}
                  className="rounded p-0.5 text-muted opacity-0 transition-opacity hover:text-ink group-hover:opacity-100 focus:opacity-100"
                  aria-label="Thêm notebook"
                >
                  <Plus className="h-3.5 w-3.5" />
                </button>
              </Tooltip>
            </div>

            {notebooksExpanded ? (
              <div className="mt-1 space-y-0.5 pl-2">
                {currentNotebooks.length === 0 ? (
                  <button
                    type="button"
                    onClick={() => setNbOpen(true)}
                    className="w-full rounded-lg px-2.5 py-1.5 text-left text-xs text-muted hover:bg-bg-hover hover:text-ink"
                  >
                    + Tạo notebook đầu tiên
                  </button>
                ) : (
                  currentNotebooks.map((nb) => {
                    const targetPath = `/knowledge/${nb.workspaceId}/notebooks/${nb.id}`
                    const isActive = location.pathname === targetPath
                    return (
                      <NavLink
                        key={nb.id}
                        to={targetPath}
                        onClick={() => setMobile(false)}
                        className={cn(
                          "flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13px] transition-colors",
                          isActive
                            ? "bg-bg-active font-semibold text-ink"
                            : "text-muted hover:bg-bg-hover hover:text-ink",
                        )}
                      >
                        <span
                          className={cn(
                            "h-1.5 w-1.5 shrink-0 rounded-full",
                            isActive ? "bg-brand" : "bg-muted/50",
                          )}
                        />
                        <span className="truncate">{nb.name}</span>
                      </NavLink>
                    )
                  })
                )}
              </div>
            ) : null}
          </div>
        </div>

        {collapsed ? <div className="hidden flex-1 md:block" /> : null}

        {/* 5. Thẻ thành viên ở đáy Sidebar giống mẫu Motivo (Sophie Moore ›) */}
        <div className="mt-auto shrink-0 border-t border-line p-3">
          <button
            type="button"
            onClick={() => {
              navigate("/settings")
              setMobile(false)
            }}
            className={cn(
              "flex w-full items-center gap-2.5 rounded-xl p-2 text-left transition-colors hover:bg-bg-hover",
              collapsed && "md:justify-center md:p-1.5",
            )}
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-soft text-xs font-bold text-brand">
              TV
            </span>
            <div className={cn("min-w-0 flex-1", collapsed && "md:hidden")}>
              <p className="truncate text-xs font-semibold text-ink">Thành viên</p>
              <p className="truncate text-[11px] text-muted">Không gian cá nhân</p>
            </div>
            <ChevronRight
              className={cn("h-3.5 w-3.5 shrink-0 text-muted", collapsed && "md:hidden")}
            />
          </button>
        </div>
      </aside>

      <NameDialog
        open={wsOpen}
        title="Tạo không gian làm việc"
        confirmLabel="Tạo"
        showDescription
        onClose={() => setWsOpen(false)}
        onSubmit={(name, description) => {
          const ws = createWorkspace(name, description)
          toast({ title: "Đã tạo không gian mới", tone: "success" })
          navigate(`/knowledge/${ws.id}`)
        }}
      />
      <NameDialog
        open={nbOpen}
        title="Thêm notebook"
        confirmLabel="Thêm"
        onClose={() => setNbOpen(false)}
        onSubmit={(name) => {
          if (currentWs) {
            createNotebook(currentWs.id, name)
            toast({ title: "Đã tạo notebook", tone: "success" })
          }
        }}
      />
    </>
  )
}

export { AppSidebar as Sidebar }
