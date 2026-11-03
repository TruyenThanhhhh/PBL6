import { useEffect, useMemo, useState } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import {
  FileText,
  GraduationCap,
  MessageSquare,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Quote,
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
  const documents = useAppStore((s) => s.documents)
  const conversations = useAppStore((s) => s.conversations)
  const current = useAppStore((s) => s.currentWorkspaceId)
  const setCitationOpen = useAppStore((s) => s.setCitationOpen)

  const createConversation = useAppStore((s) => s.createConversation)
  const renameConversation = useAppStore((s) => s.renameConversation)
  const deleteConversation = useAppStore((s) => s.deleteConversation)
  const toast = useAppStore((s) => s.toast)

  const navigate = useNavigate()
  const location = useLocation()

  // Theo dõi khi người dùng chủ động chọn mục Citation trên Sidebar để chỉ highlight duy nhất 1 mục
  const [citationNavSelected, setCitationNavSelected] = useState(false)
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

  const recentDocuments = useMemo(
    () =>
      [...documents]
        .filter((d) => d.workspaceId === currentWsId)
        .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
        .slice(0, 5),
    [documents, currentWsId],
  )

  const handleNewChat = () => {
    setCitationNavSelected(false)
    const conv = createConversation(currentWsId, "Cuộc trò chuyện mới")
    navigate(`/chat/${conv.id}`)
    setMobile(false)
  }

  const isDocsRoute =
    location.pathname === "/documents" || location.pathname.startsWith("/documents/")
  const isStudyRoute = location.pathname === "/study"
  const isChatRoute =
    !isDocsRoute &&
    !isStudyRoute &&
    (location.pathname === "/chat" ||
      location.pathname.startsWith("/chat/") ||
      location.pathname === "/studio" ||
      location.pathname === "/dashboard")

  // Chỉ highlight duy nhất 1 mục đang active
  const activeNavId: "chat" | "documents" | "citation" | "study" = isDocsRoute
    ? "documents"
    : isStudyRoute
      ? "study"
      : citationNavSelected && isChatRoute
        ? "citation"
        : "chat"

  const navItems = [
    {
      id: "chat" as const,
      label: "Chat AI",
      icon: MessageSquare,
      onClick: () => {
        setCitationNavSelected(false)
        navigate("/chat")
        setMobile(false)
      },
    },
    {
      id: "documents" as const,
      label: "Tài liệu",
      icon: FileText,
      onClick: () => {
        setCitationNavSelected(false)
        navigate("/documents")
        setMobile(false)
      },
    },
    {
      id: "citation" as const,
      label: "Citation",
      icon: Quote,
      onClick: () => {
        setCitationNavSelected(true)
        setCitationOpen(true)
        window.dispatchEvent(new CustomEvent("studio-context-tab", { detail: "citations" }))
        if (!isChatRoute) {
          navigate("/chat")
        }
        setMobile(false)
      },
    },
    {
      id: "study" as const,
      label: "Học liệu",
      icon: GraduationCap,
      onClick: () => {
        setCitationNavSelected(false)
        navigate("/study")
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
          className="fixed inset-0 z-30 bg-[#172B29]/30 md:hidden"
          aria-label="Đóng menu điều hướng"
          onClick={() => setMobile(false)}
        />
      ) : null}

      <aside
        aria-label="Thanh điều hướng Workspace Studio"
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex h-full shrink-0 flex-col border-r border-[#D4E2DF] bg-[#F0F5F4] text-[13px] transition-[width,transform] duration-150 md:static md:translate-x-0",
          collapsed ? "w-[236px] md:w-[60px]" : "w-[236px]",
          mobile ? "translate-x-0" : "-translate-x-full md:translate-x-0",
        )}
      >
        {/* Nút Hội thoại mới (CTA Primary #087F73) + Nút thu gọn Sidebar */}
        <div
          className={cn(
            "flex items-center justify-between gap-2 px-3 pt-3 pb-2",
            collapsed && "md:flex-col md:justify-center md:px-2",
          )}
        >
          {collapsed ? (
            <Tooltip content="Mở rộng thanh bên" side="right">
              <button
                type="button"
                onClick={toggle}
                className="hidden h-8 w-8 items-center justify-center rounded-lg text-[#647C79] transition-colors hover:bg-white hover:text-[#172B29] md:flex"
                aria-label="Mở rộng Sidebar"
              >
                <PanelLeftOpen className="h-4 w-4" />
              </button>
            </Tooltip>
          ) : null}

          <Tooltip content="Tạo cuộc trò chuyện mới" side={collapsed ? "right" : "bottom"}>
            <button
              type="button"
              onClick={handleNewChat}
              className={cn(
                "inline-flex items-center justify-center gap-1.5 rounded-lg bg-[#087F73] text-xs font-semibold text-white transition-colors hover:bg-[#06665C]",
                collapsed ? "h-8 w-8 md:px-0" : "h-8 flex-1 px-3",
              )}
              aria-label="Hội thoại mới"
            >
              <Plus className="h-3.5 w-3.5 shrink-0" />
              <span className={cn("truncate", collapsed && "md:hidden")}>Hội thoại mới</span>
            </button>
          </Tooltip>

          {!collapsed ? (
            <Tooltip content="Thu gọn thanh bên" side="bottom">
              <Button
                variant="ghost"
                size="icon"
                className="hidden h-8 w-8 shrink-0 text-[#647C79] hover:bg-[#E3ECEA] hover:text-[#172B29] md:inline-flex"
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
            className="h-8 w-8 shrink-0 text-[#647C79] md:hidden"
            onClick={() => setMobile(false)}
            aria-label="Đóng menu"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* 1. Menu chính: Chỉ highlight duy nhất 1 mục đang active */}
        <nav className="flex shrink-0 flex-col gap-0.5 px-2.5 py-1.5" aria-label="Chức năng Studio">
          {navItems.map((item) => {
            const active = activeNavId === item.id
            const btn = (
              <button
                key={item.id}
                type="button"
                onClick={item.onClick}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors",
                  active
                    ? "bg-white font-semibold text-[#172B29] shadow-[0_1px_2px_rgba(23,43,41,0.06)] ring-1 ring-[#D4E2DF]"
                    : "font-medium text-[#647C79] hover:bg-[#E5EEEC] hover:text-[#172B29]",
                  collapsed && "md:justify-center md:px-2",
                )}
              >
                <item.icon
                  className={cn(
                    "h-4 w-4 shrink-0",
                    active ? "text-[#087F73]" : "text-[#647C79]",
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

        {/* 2. Lịch sử hội thoại & 3–5 Tài liệu gần đây (Typography nhỏ gọn, sạch sẽ) */}
        <div
          className={cn(
            "mt-1 flex-1 space-y-5 overflow-y-auto border-t border-[#D4E2DF] px-2.5 py-3",
            collapsed && "md:hidden",
          )}
        >
          {/* Lịch sử hội thoại */}
          <div>
            <div className="mb-1 flex items-center justify-between px-2">
              <span className="text-[11px] font-semibold text-[#647C79]">
                Lịch sử hội thoại
              </span>
              <button
                type="button"
                onClick={handleNewChat}
                className="rounded p-0.5 text-[#647C79] transition-colors hover:text-[#172B29]"
                title="Hội thoại mới"
                aria-label="Hội thoại mới"
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            </div>

            {wsConversations.length === 0 ? (
              <p className="px-2 py-1 text-xs text-[#647C79]">Chưa có hội thoại</p>
            ) : (
              <ul className="space-y-0.5">
                {wsConversations.map((c) => {
                  const active = isChatRoute && c.id === activeConvId
                  return (
                    <li
                      key={c.id}
                      className={cn(
                        "group flex items-center justify-between gap-1 rounded-md px-2 py-1 text-xs transition-colors",
                        active
                          ? "font-semibold text-[#087F73]"
                          : "text-[#647C79] hover:bg-[#E5EEEC] hover:text-[#172B29]",
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => {
                          setCitationNavSelected(false)
                          navigate(`/chat/${c.id}`)
                          setMobile(false)
                        }}
                        className="min-w-0 flex-1 truncate text-left"
                      >
                        {c.title}
                      </button>

                      <DropdownMenu
                        align="end"
                        trigger={
                          <button
                            type="button"
                            aria-label={`Tùy chọn cho ${c.title}`}
                            className="rounded p-0.5 text-[#647C79] opacity-0 transition-opacity hover:text-[#172B29] group-hover:opacity-100 focus:opacity-100"
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

          {/* Tài liệu gần đây (3-5 tài liệu) */}
          <div>
            <div className="mb-1 flex items-center justify-between px-2">
              <span className="text-[11px] font-semibold text-[#647C79]">
                Tài liệu gần đây
              </span>
              <button
                type="button"
                onClick={() => {
                  setCitationNavSelected(false)
                  navigate("/documents")
                  setMobile(false)
                }}
                className="text-[11px] font-medium text-[#087F73] hover:underline"
              >
                Xem hết
              </button>
            </div>

            {recentDocuments.length === 0 ? (
              <p className="px-2 py-1 text-xs text-[#647C79]">Chưa có tài liệu</p>
            ) : (
              <ul className="space-y-0.5">
                {recentDocuments.map((doc) => {
                  const isDocActive = location.pathname === `/documents/${doc.id}`
                  return (
                    <li key={doc.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setCitationNavSelected(false)
                          navigate(`/documents/${doc.id}`)
                          setMobile(false)
                        }}
                        title={doc.fileName}
                        className={cn(
                          "flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs transition-colors",
                          isDocActive
                            ? "font-semibold text-[#087F73]"
                            : "text-[#647C79] hover:bg-[#E5EEEC] hover:text-[#172B29]",
                        )}
                      >
                        <FileText className="h-3 w-3 shrink-0 text-[#647C79]" />
                        <span className="flex-1 truncate">{doc.fileName}</span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </div>
      </aside>

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
