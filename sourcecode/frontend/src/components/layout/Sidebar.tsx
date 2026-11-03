import { useEffect, useMemo, useState } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import {
  GraduationCap,
  MessageSquare,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Telescope,
  Trash2,
  X,
} from "lucide-react"
import { ConfirmDialog, NameDialog } from "@/components/common/NameDialog"
import {
  Button,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuSeparator,
  Tooltip,
} from "@/components/ui"
import { useAppStore } from "@/store/app-store"
import type { Conversation } from "@/types"
import { cn } from "@/utils/cn"

export function AppSidebar() {
  const collapsed = useAppStore((s) => s.sidebarCollapsed)
  const toggle = useAppStore((s) => s.toggleSidebar)
  const mobile = useAppStore((s) => s.mobileNavOpen)
  const setMobile = useAppStore((s) => s.setMobileNavOpen)

  const workspaces = useAppStore((s) => s.workspaces)
  const conversations = useAppStore((s) => s.conversations)
  const current = useAppStore((s) => s.currentWorkspaceId)

  const createConversation = useAppStore((s) => s.createConversation)
  const renameConversation = useAppStore((s) => s.renameConversation)
  const deleteConversation = useAppStore((s) => s.deleteConversation)
  const toast = useAppStore((s) => s.toast)

  const navigate = useNavigate()
  const location = useLocation()

  const [renameTarget, setRenameTarget] = useState<Conversation | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null)

  useEffect(() => {
    if (!mobile) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMobile(false)
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [mobile, setMobile])

  const currentWs = workspaces.find((w) => w.id === current) ?? workspaces[0]
  const currentWsId = currentWs?.id ?? "ws_default"

  const wsConversations = useMemo(
    () => conversations.filter((c) => c.workspaceId === currentWsId),
    [conversations, currentWsId],
  )

  const handleNewChat = () => {
    const conv = createConversation(currentWsId, "Cuộc trò chuyện mới")
    navigate(`/chat/${conv.id}`)
    setMobile(false)
  }

  // Chỉ 1 mục được active nền màu tại 1 thời điểm: 1. Chat AI | 2. Học liệu | 3. Nghiên cứu
  const activeMode: "chat" | "study" | "research" = useMemo(() => {
    if (location.pathname.startsWith("/study")) return "study"
    if (location.pathname.startsWith("/research")) return "research"
    return "chat"
  }, [location.pathname])

  const navItems = [
    {
      id: "chat" as const,
      label: "Chat AI",
      icon: MessageSquare,
      onClick: () => {
        navigate("/chat")
        setMobile(false)
      },
    },
    {
      id: "study" as const,
      label: "Học liệu (Study Studio)",
      icon: GraduationCap,
      onClick: () => {
        navigate("/study")
        setMobile(false)
      },
    },
    {
      id: "research" as const,
      label: "Nghiên cứu (Research)",
      icon: Telescope,
      onClick: () => {
        navigate("/research")
        setMobile(false)
      },
    },
  ]

  const activeConvId = useMemo(() => {
    const parts = location.pathname.split("/").filter(Boolean)
    if (parts[0] === "chat" && parts[1]) return parts[1]
    return wsConversations[0]?.id ?? null
  }, [location.pathname, wsConversations])

  return (
    <>
      {mobile ? (
        <button
          type="button"
          className="fixed inset-0 z-30 bg-slate-900/30 md:hidden"
          aria-label="Đóng menu điều hướng"
          onClick={() => setMobile(false)}
        />
      ) : null}

      <aside
        aria-label="Thanh điều hướng Workspace Studio"
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex h-full shrink-0 flex-col border-r border-slate-200/80 bg-[#F8FAFC] text-[13px] transition-[width,transform] duration-150 md:static md:translate-x-0",
          collapsed ? "w-[238px] md:w-[60px]" : "w-[238px]",
          mobile ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        {/* Nút tạo hội thoại mới + Thu gọn Sidebar */}
        <div
          className={cn(
            "flex items-center justify-between gap-1.5 px-3 pt-3 pb-2",
            collapsed && "md:flex-col md:justify-center md:px-2",
          )}
        >
          {collapsed ? (
            <Tooltip content="Mở rộng thanh bên" side="right">
              <button
                type="button"
                onClick={toggle}
                className="hidden h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 transition-colors hover:border-[#2563EB] hover:text-[#2563EB] md:flex"
                aria-label="Mở rộng Sidebar"
              >
                <PanelLeftOpen className="h-4 w-4" />
              </button>
            </Tooltip>
          ) : null}

          <Tooltip content="Bắt đầu cuộc trò chuyện AI mới" side={collapsed ? "right" : "bottom"}>
            <button
              type="button"
              onClick={handleNewChat}
              className={cn(
                "inline-flex items-center justify-center gap-2 rounded-xl bg-[#2563EB] text-xs font-semibold text-white shadow-2xs transition-colors hover:bg-[#1D4ED8]",
                collapsed ? "h-9 w-9 md:px-0" : "h-9 flex-1 px-3",
              )}
              aria-label="Hội thoại mới"
            >
              <Plus className="h-4 w-4 shrink-0" />
              <span className={cn("truncate", collapsed && "md:hidden")}>Hội thoại mới</span>
            </button>
          </Tooltip>

          {!collapsed ? (
            <Tooltip content="Thu gọn thanh bên" side="bottom">
              <Button
                variant="ghost"
                size="icon"
                className="hidden h-8 w-8 shrink-0 text-slate-500 hover:bg-slate-200/60 hover:text-slate-900 md:inline-flex"
                onClick={toggle}
                aria-label="Thu gọn Sidebar"
              >
                <PanelLeftClose className="h-4 w-4" />
              </Button>
            </Tooltip>
          ) : null}

          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 text-slate-500 md:hidden"
            onClick={() => setMobile(false)}
            aria-label="Đóng menu"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* 1. Menu chuyển đổi 3 không gian chính: 1. Chat AI | 2. Học liệu | 3. Nghiên cứu */}
        <nav className="flex shrink-0 flex-col gap-1 px-2.5 py-1.5" aria-label="Chế độ Studio">
          {navItems.map((item) => {
            const isActive = activeMode === item.id
            const btn = (
              <button
                key={item.id}
                type="button"
                onClick={item.onClick}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-[13px] transition-all",
                  isActive
                    ? "bg-[#EFF6FF] font-semibold text-[#2563EB] ring-1 ring-[#BFDBFE]/80"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
                  collapsed && "md:justify-center md:px-2",
                )}
              >
                <item.icon
                  className={cn(
                    "h-4 w-4 shrink-0",
                    isActive ? "text-[#2563EB]" : "text-slate-400",
                  )}
                />
                <span className={cn("flex-1 truncate", collapsed && "md:hidden")}>
                  {item.label}
                </span>
              </button>
            )

            return collapsed ? (
              <Tooltip key={item.id} content={item.label} side="right">
                {btn}
              </Tooltip>
            ) : (
              btn
            )
          })}
        </nav>

        {/* 2. Vùng Lịch sử hội thoại rộng rãi (chiếm toàn bộ không gian còn lại ở cột trái) */}
        <div
          className={cn(
            "studio-scroll mt-1 flex-1 overflow-y-auto border-t border-slate-200/70 px-2.5 py-3",
            collapsed && "md:hidden",
          )}
        >
          <div className="mb-2 flex items-center justify-between px-2">
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Lịch sử hội thoại ({wsConversations.length})
            </span>
            <button
              type="button"
              onClick={handleNewChat}
              className="rounded p-0.5 text-slate-400 transition-colors hover:bg-slate-200/60 hover:text-[#2563EB]"
              title="Tạo cuộc trò chuyện mới"
              aria-label="Tạo cuộc trò chuyện mới"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>

          {wsConversations.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-200 bg-white/70 p-4 text-center">
              <p className="text-xs text-slate-500">Chưa có phiên hội thoại nào.</p>
              <button
                type="button"
                onClick={handleNewChat}
                className="mt-1.5 inline-flex items-center gap-1 text-xs font-semibold text-[#2563EB] hover:underline"
              >
                <Plus className="h-3 w-3" />
                <span>Bắt đầu phiên mới</span>
              </button>
            </div>
          ) : (
            <ul className="space-y-1">
              {wsConversations.map((c) => {
                const active = activeMode === "chat" && c.id === activeConvId
                return (
                  <li
                    key={c.id}
                    className={cn(
                      "group flex items-center justify-between gap-1 rounded-xl px-2.5 py-2 text-xs transition-colors",
                      active
                        ? "bg-white font-semibold text-slate-900 shadow-2xs ring-1 ring-slate-200"
                        : "text-slate-600 hover:bg-slate-100/90 hover:text-slate-900",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        navigate(`/chat/${c.id}`)
                        setMobile(false)
                      }}
                      className="flex min-w-0 flex-1 items-center gap-2 text-left"
                    >
                      <MessageSquare
                        className={cn(
                          "h-3.5 w-3.5 shrink-0",
                          active ? "text-[#2563EB]" : "text-slate-400",
                        )}
                      />
                      <span className="truncate">{c.title}</span>
                    </button>

                    <DropdownMenu
                      align="end"
                      trigger={
                        <button
                          type="button"
                          aria-label={`Tùy chọn cho ${c.title}`}
                          className="rounded p-0.5 text-slate-400 opacity-0 transition-opacity hover:bg-slate-100 hover:text-slate-900 group-hover:opacity-100 focus:opacity-100"
                        >
                          <MoreHorizontal className="h-3.5 w-3.5" />
                        </button>
                      }
                    >
                      <DropdownMenuItem
                        icon={<Pencil className="h-3.5 w-3.5" />}
                        onClick={() => setRenameTarget(c)}
                      >
                        Đổi tên
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        tone="danger"
                        icon={<Trash2 className="h-3.5 w-3.5" />}
                        onClick={() => setDeleteTarget(c)}
                      >
                        Xóa
                      </DropdownMenuItem>
                    </DropdownMenu>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </aside>

      {/* Dialog đổi tên hội thoại */}
      <NameDialog
        open={Boolean(renameTarget)}
        title="Đổi tên cuộc trò chuyện"
        initialName={renameTarget?.title ?? ""}
        onClose={() => setRenameTarget(null)}
        onSubmit={(name) => {
          if (renameTarget) {
            renameConversation(renameTarget.id, name)
            toast({ title: "Đã đổi tên hội thoại", description: name, tone: "success" })
            setRenameTarget(null)
          }
        }}
      />

      {/* Dialog xóa hội thoại */}
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Xóa cuộc trò chuyện?"
        description={
          deleteTarget
            ? `Bạn có chắc muốn xóa cuộc trò chuyện "${deleteTarget.title}"?`
            : undefined
        }
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (!deleteTarget) return
          const targetId = deleteTarget.id
          deleteConversation(targetId)
          setDeleteTarget(null)
          toast({ title: "Đã xóa cuộc trò chuyện", tone: "info" })
          if (activeConvId === targetId) {
            const remaining = wsConversations.filter((c) => c.id !== targetId)
            navigate(remaining[0] ? `/chat/${remaining[0].id}` : "/chat")
          }
        }}
      />
    </>
  )
}
