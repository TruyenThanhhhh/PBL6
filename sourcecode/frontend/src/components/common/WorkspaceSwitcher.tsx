import { useState } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import { Check, ChevronDown, FolderOpen, FolderPlus, Layers } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui"
import { NameDialog } from "@/components/common/NameDialog"
import { useAppStore } from "@/store/app-store"
import { cn } from "@/utils/cn"

interface WorkspaceSwitcherProps {
  variant?: "header" | "pill" | "banner" | "sidebar"
  className?: string
  align?: "start" | "end"
  onSwitch?: (workspaceId: string) => void
}

export function WorkspaceSwitcher({
  variant = "pill",
  className,
  align = "start",
  onSwitch,
}: WorkspaceSwitcherProps) {
  const navigate = useNavigate()
  const location = useLocation()

  const workspaces = useAppStore((s) => s.workspaces)
  const currentId = useAppStore((s) => s.currentWorkspaceId)
  const setCurrent = useAppStore((s) => s.setCurrentWorkspace)
  const createWorkspace = useAppStore((s) => s.createWorkspace)
  const documents = useAppStore((s) => s.documents)
  const conversations = useAppStore((s) => s.conversations)
  const toast = useAppStore((s) => s.toast)

  const [createOpen, setCreateOpen] = useState(false)

  const currentWs = workspaces.find((w) => w.id === currentId) ?? workspaces[0]
  const currentDocCount = documents.filter((d) => d.workspaceId === currentWs?.id).length

  const handleSelectWorkspace = (targetId: string) => {
    if (targetId === currentWs?.id) return
    setCurrent(targetId)
    onSwitch?.(targetId)

    const targetWs = workspaces.find((w) => w.id === targetId)
    toast({
      title: "Đã chuyển không gian làm việc",
      description: `Đang làm việc trên: ${targetWs?.name ?? "Không gian mới"}`,
      tone: "info",
    })

    // Nếu đang ở trang chi tiết workspace cũ, tự động điều hướng sang workspace mới
    if (location.pathname.startsWith("/knowledge/") && location.pathname !== "/knowledge") {
      navigate(`/knowledge/${targetId}`)
      return
    }

    // Nếu đang ở màn hình chat với ID cụ thể, kiểm tra xem conversation đó có thuộc workspace mới không
    if (location.pathname.startsWith("/chat/")) {
      const convInNewWs = conversations.find((c) => c.workspaceId === targetId)
      if (convInNewWs) {
        navigate(`/chat/${convInNewWs.id}`)
      } else {
        navigate("/chat")
      }
    }
  }

  // Render Trigger Button theo từng variant
  const renderTrigger = () => {
    if (variant === "header") {
      return (
        <button
          type="button"
          className={cn(
            "group inline-flex h-8 items-center gap-1.5 rounded-lg border border-line/70 bg-bg-secondary/60 px-2.5 text-xs font-medium text-ink transition-all hover:border-brand/40 hover:bg-bg-hover focus:outline-hidden",
            className,
          )}
          aria-label="Chọn không gian làm việc"
        >
          <span className="flex h-4 w-4 shrink-0 items-center justify-center text-brand">
            <FolderOpen className="h-3.5 w-3.5" />
          </span>
          <span className="hidden text-muted/70 sm:inline">Không gian:</span>
          <span className="max-w-[140px] truncate font-semibold text-ink md:max-w-[190px]">
            {currentWs?.name ?? "Không gian mặc định"}
          </span>
          <ChevronDown className="h-3 w-3 shrink-0 text-muted transition-transform group-hover:text-ink" />
        </button>
      )
    }

    if (variant === "banner") {
      return (
        <button
          type="button"
          className={cn(
            "group flex w-full items-center justify-between gap-3 rounded-2xl border border-line bg-card/60 p-3.5 text-left transition-all hover:border-brand/50 hover:bg-bg-hover/50 sm:p-4",
            className,
          )}
          aria-label="Đổi không gian làm việc"
        >
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand shadow-xs">
              <FolderOpen className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                  Không gian làm việc đang chọn
                </span>
                <span className="rounded-full bg-brand-soft px-2 py-0.5 text-[10px] font-bold text-brand">
                  Đang hoạt động
                </span>
              </div>
              <h2 className="truncate text-base font-bold text-ink sm:text-lg">
                {currentWs?.name ?? "Không gian mặc định"}
              </h2>
              <p className="mt-0.5 truncate text-xs text-muted">
                {currentDocCount} tài liệu · Dữ liệu được bảo vệ và cô lập riêng
              </p>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1.5 rounded-xl border border-line/80 bg-bg px-3 py-1.5 text-xs font-semibold text-ink transition-colors group-hover:border-brand/40 group-hover:text-brand">
            <span>Đổi không gian</span>
            <ChevronDown className="h-3.5 w-3.5" />
          </div>
        </button>
      )
    }

    if (variant === "sidebar") {
      return (
        <button
          type="button"
          className={cn(
            "group flex w-full items-center gap-2.5 rounded-xl p-1.5 text-left transition-colors hover:bg-bg-hover",
            className,
          )}
          aria-label="Chuyển đổi không gian làm việc"
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-soft text-brand">
            <FolderOpen className="h-4 w-4" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1">
              <span className="truncate text-xs font-bold text-ink">
                {currentWs?.name ?? "Không gian cá nhân"}
              </span>
              <ChevronDown className="h-3 w-3 shrink-0 text-muted" />
            </div>
            <p className="truncate text-[10px] text-muted">
              {currentDocCount} tài liệu
            </p>
          </div>
        </button>
      )
    }

    // Default: "pill"
    return (
      <button
        type="button"
        className={cn(
          "group inline-flex items-center gap-2 rounded-full border border-line bg-bg px-3 py-1.5 text-xs font-medium text-ink shadow-2xs transition-all hover:border-brand/40 hover:bg-bg-hover focus:outline-hidden",
          className,
        )}
        aria-label="Chọn không gian làm việc"
      >
        <span className="flex h-4 w-4 shrink-0 items-center justify-center text-brand">
          <FolderOpen className="h-3.5 w-3.5" />
        </span>
        <span className="max-w-[160px] truncate font-semibold text-ink sm:max-w-[220px]">
          {currentWs?.name ?? "Không gian mặc định"}
        </span>
        <span className="rounded-full bg-brand-soft px-1.5 py-0.2 text-[10px] font-bold text-brand">
          {currentDocCount} doc
        </span>
        <ChevronDown className="h-3 w-3 shrink-0 text-muted transition-transform group-hover:text-ink" />
      </button>
    )
  }

  return (
    <>
      <DropdownMenu align={align} trigger={renderTrigger()}>
        <DropdownMenuLabel>
          <div className="flex items-center justify-between">
            <span>Không gian làm việc</span>
            <span className="text-[10px] font-normal text-muted">Cô lập dữ liệu</span>
          </div>
        </DropdownMenuLabel>

        {workspaces.map((w) => {
          const isSelected = w.id === currentWs?.id
          const docCount = documents.filter((d) => d.workspaceId === w.id).length
          const chatCount = conversations.filter((c) => c.workspaceId === w.id).length

          return (
            <DropdownMenuItem
              key={w.id}
              onClick={() => handleSelectWorkspace(w.id)}
              className="flex items-center justify-between gap-3 py-2"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className={cn("truncate font-medium", isSelected && "font-bold text-brand")}>
                    {w.name}
                  </span>
                  {isSelected ? (
                    <span className="rounded bg-brand/15 px-1.5 py-0.2 text-[10px] font-semibold text-brand">
                      Đang chọn
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 truncate text-[11px] text-muted">
                  {docCount} tài liệu · {chatCount} hội thoại
                </p>
              </div>

              {isSelected ? (
                <Check className="h-4 w-4 shrink-0 text-brand" />
              ) : null}
            </DropdownMenuItem>
          )
        })}

        <DropdownMenuSeparator />

        <DropdownMenuItem
          icon={<FolderPlus className="h-3.5 w-3.5 text-brand" />}
          onClick={() => setCreateOpen(true)}
        >
          Tạo không gian mới...
        </DropdownMenuItem>

        <DropdownMenuItem
          icon={<Layers className="h-3.5 w-3.5 text-muted" />}
          onClick={() => navigate("/knowledge")}
        >
          Quản lý tất cả không gian
        </DropdownMenuItem>
      </DropdownMenu>

      <NameDialog
        open={createOpen}
        title="Tạo không gian làm việc mới"
        confirmLabel="Tạo không gian"
        showDescription
        onClose={() => setCreateOpen(false)}
        onSubmit={(name, description) => {
          const ws = createWorkspace(name, description)
          setCurrent(ws.id)
          toast({
            title: "Đã tạo không gian mới",
            description: `Đang làm việc trên: ${ws.name}`,
            tone: "success",
          })
          onSwitch?.(ws.id)
        }}
      />
    </>
  )
}
