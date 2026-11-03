import { useEffect, useMemo, useState } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import {
  BookOpen,
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
  const citationOpen = useAppStore((s) => s.citationOpen)
  const setCitationOpen = useAppStore((s) => s.setCitationOpen)

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

  const recentDocuments = useMemo(
    () =>
      [...documents]
        .filter((d) => d.workspaceId === currentWsId)
        .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
        .slice(0, 5),
    [documents, currentWsId],
  )

  const totalWsDocs = useMemo(
    () => documents.filter((d) => d.workspaceId === currentWsId).length,
    [documents, currentWsId],
  )

  const handleNewChat = () => {
    const conv = createConversation(currentWsId, "Cuộc trò chuyện mới")
    navigate(`/chat/${conv.id}`)
    setMobile(false)
  }

  const handleOpenCitations = () => {
    setCitationOpen(true)
    window.dispatchEvent(new CustomEvent("studio-context-tab", { detail: "citations" }))
    if (!location.pathname.startsWith("/chat")) {
      navigate("/chat")
    }
    setMobile(false)
  }

  const isChatRoute =
    location.pathname === "/chat" ||
    location.pathname.startsWith("/chat/") ||
    location.pathname === "/dashboard"
  const isDocsRoute =
    location.pathname === "/documents" || location.pathname.startsWith("/documents/")
  const isStudyRoute = location.pathname === "/study"

  const navItems = [
    {
      id: "chat",
      label: "Chat AI",
      icon: MessageSquare,
      active: isChatRoute,
      badge: wsConversations.length > 0 ? String(wsConversations.length) : undefined,
      onClick: () => {
        navigate("/chat")
        setMobile(false)
      },
    },
    {
      id: "documents",
      label: "Tài liệu",
      icon: FileText,
      active: isDocsRoute,
      badge: totalWsDocs > 0 ? String(totalWsDocs) : undefined,
      onClick: () => {
        navigate("/documents")
        setMobile(false)
      },
    },
    {
      id: "citation",
      label: "Citation",
      icon: Quote,
      active: isChatRoute && citationOpen,
      onClick: handleOpenCitations,
    },
    {
      id: "study",
      label: "Học liệu",
      icon: GraduationCap,
      active: isStudyRoute,
      onClick: () => {
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
          className="fixed inset-0 z-30 bg-[#0B1716]/30 md:hidden"
          aria-label="Đóng menu điều hướng"
          onClick={() => setMobile(false)}
        />
      ) : null}

      <aside
        aria-label="Thanh điều hướng Workspace Studio"
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex h-full shrink-0 flex-col border-r border-[#DCECE8] bg-[#F7FAF9] text-[13px] transition-[width,transform] duration-150 md:static md:translate-x-0",
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
                className="hidden h-9 w-9 items-center justify-center rounded-xl border border-[#D5E6E2] bg-white text-[#37524F] transition-colors hover:border-[#0F766E] hover:text-[#0F766E] md:flex"
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
                "inline-flex items-center justify-center gap-2 rounded-xl bg-[#0B1315] text-xs font-semibold text-white shadow-2xs transition-colors hover:bg-[#0F766E]",
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
                className="hidden h-8 w-8 shrink-0 text-[#647D7A] hover:bg-[#EAF4F2] hover:text-[#0B1716] md:inline-flex"
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
            className="h-8 w-8 shrink-0 text-[#647D7A] md:hidden"
            onClick={() => setMobile(false)}
            aria-label="Đóng menu"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* 1. Menu chính của Studio: Chat AI, Tài liệu, Citation, Học liệu */}
        <nav className="flex shrink-0 flex-col gap-0.5 px-2.5 py-1" aria-label="Chức năng Studio">
          {navItems.map((item) => {
            const btn = (
              <button
                key={item.id}
                type="button"
                onClick={item.onClick}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-[13px] transition-all",
                  item.active
                    ? "bg-[#E2F3EF] font-semibold text-[#0B1716]"
                    : "text-[#526B68] hover:bg-[#EDF6F4] hover:text-[#0B1716]",
                  collapsed && "md:justify-center md:px-2",
                )}
              >
                <item.icon
                  className={cn(
                    "h-4 w-4 shrink-0",
                    item.active ? "text-[#0F766E]" : "text-[#647D7A]",
                  )}
                />
                <span className={cn("flex-1 truncate", collapsed && "md:hidden")}>
                  {item.label}
                </span>
                {item.badge && !collapsed ? (
                  <span
                    className={cn(
                      "rounded-full px-1.5 py-0.2 text-[10px] font-semibold",
                      item.active
                        ? "bg-white text-[#0F766E]"
                        : "bg-[#E6F0EE] text-[#526B68]",
                    )}
                  >
                    {item.badge}
                  </span>
                ) : null}
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

        {/* Vùng cuộn: Lịch sử hội thoại + 3–5 Tài liệu gần đây (ẩn khi thu gọn) */}
        <div
          className={cn(
            "mt-2 flex-1 space-y-5 overflow-y-auto border-t border-[#E4EFECE0] px-2.5 py-3",
            collapsed && "md:hidden",
          )}
        >
          {/* 2. Danh sách lịch sử hội thoại */}
          <div>
            <div className="mb-1.5 flex items-center justify-between px-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#647D7A]">
                Lịch sử hội thoại
              </span>
              <button
                type="button"
                onClick={handleNewChat}
                className="rounded p-0.5 text-[#647D7A] transition-colors hover:bg-[#E6F0EE] hover:text-[#0F766E]"
                title="Tạo cuộc trò chuyện mới"
                aria-label="Tạo cuộc trò chuyện mới"
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            </div>

            {wsConversations.length === 0 ? (
              <p className="px-2 py-2 text-xs text-[#7A9490]">Chưa có hội thoại nào.</p>
            ) : (
              <ul className="space-y-0.5">
                {wsConversations.map((c) => {
                  const active = isChatRoute && c.id === activeConvId
                  return (
                    <li
                      key={c.id}
                      className={cn(
                        "group flex items-center justify-between gap-1 rounded-lg px-2 py-1.5 text-xs transition-colors",
                        active
                          ? "bg-white font-semibold text-[#0B1716] shadow-2xs ring-1 ring-[#DCECE8]"
                          : "text-[#4A6663] hover:bg-[#EDF6F4] hover:text-[#0B1716]",
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
                            active ? "text-[#0F766E]" : "text-[#829B98]",
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
                            className="rounded p-0.5 text-[#7A9490] opacity-0 transition-opacity hover:bg-[#E6F0EE] hover:text-[#0B1716] group-hover:opacity-100 focus:opacity-100"
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

          {/* 3. Danh sách 3–5 tài liệu gần đây */}
          <div>
            <div className="mb-1.5 flex items-center justify-between px-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#647D7A]">
                Tài liệu gần đây
              </span>
              <button
                type="button"
                onClick={() => {
                  navigate("/documents")
                  setMobile(false)
                }}
                className="text-[11px] font-medium text-[#0F766E] hover:underline"
              >
                Tất cả ({totalWsDocs})
              </button>
            </div>

            {recentDocuments.length === 0 ? (
              <div className="rounded-xl border border-dashed border-[#CBE4DF] bg-white/60 p-3 text-center">
                <p className="text-xs text-[#647D7A]">Chưa có tài liệu</p>
                <button
                  type="button"
                  onClick={() => {
                    navigate("/documents")
                    setMobile(false)
                  }}
                  className="mt-1.5 inline-flex items-center gap-1 text-xs font-semibold text-[#0F766E] hover:underline"
                >
                  <Plus className="h-3 w-3" />
                  <span>Tải tài liệu</span>
                </button>
              </div>
            ) : (
              <ul className="space-y-0.5">
                {recentDocuments.map((doc) => {
                  const isDocActive = location.pathname === `/documents/${doc.id}`
                  return (
                    <li key={doc.id}>
                      <button
                        type="button"
                        onClick={() => {
                          navigate(`/documents/${doc.id}`)
                          setMobile(false)
                        }}
                        title={doc.fileName}
                        className={cn(
                          "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors",
                          isDocActive
                            ? "bg-white font-semibold text-[#0B1716] shadow-2xs ring-1 ring-[#DCECE8]"
                            : "text-[#4A6663] hover:bg-[#EDF6F4] hover:text-[#0B1716]",
                        )}
                      >
                        <BookOpen className="h-3.5 w-3.5 shrink-0 text-[#0F766E]" />
                        <span className="flex-1 truncate">{doc.fileName}</span>
                        <span
                          className={cn(
                            "h-1.5 w-1.5 shrink-0 rounded-full",
                            doc.status === "ready"
                              ? "bg-[#10B981]"
                              : doc.status === "failed"
                                ? "bg-rose-500"
                                : "bg-amber-400",
                          )}
                        />
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
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
