import { useMemo, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import {
  Activity,
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronRight,
  FileUp,
  FolderOpen,
  Menu,
  Moon,
  MoreHorizontal,
  Pencil,
  Settings,
  Sun,
  Trash2,
} from "lucide-react"
import { ConfirmDialog, NameDialog } from "@/components/common/NameDialog"
import {
  Button,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  Tooltip,
} from "@/components/ui"
import { hasDuplicateName } from "@/features/workspaces/workspace-utils"
import { useAppStore } from "@/store/app-store"
import { cn } from "@/utils/cn"

export function AppHeader() {
  const navigate = useNavigate()
  const setMobile = useAppStore((s) => s.setMobileNavOpen)
  const status = useAppStore((s) => s.status)
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const localLlmModel = useAppStore((s) => s.localLlmModel)

  const workspaces = useAppStore((s) => s.workspaces)
  const documents = useAppStore((s) => s.documents)
  const currentWorkspaceId = useAppStore((s) => s.currentWorkspaceId)
  const setCurrentWorkspace = useAppStore((s) => s.setCurrentWorkspace)
  const updateWorkspace = useAppStore((s) => s.updateWorkspace)
  const deleteWorkspace = useAppStore((s) => s.deleteWorkspace)
  const toast = useAppStore((s) => s.toast)

  const [editOpen, setEditOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  const currentWs = useMemo(
    () => workspaces.find((w) => w.id === currentWorkspaceId) ?? workspaces[0],
    [workspaces, currentWorkspaceId],
  )

  const wsDocuments = useMemo(
    () => documents.filter((d) => d.workspaceId === currentWs?.id),
    [documents, currentWs?.id],
  )

  const readyCount = wsDocuments.filter((d) => d.status === "ready").length
  const processingCount = wsDocuments.filter(
    (d) => d.status !== "ready" && d.status !== "failed",
  ).length

  const activeModelName = status.ollamaModels[0] || localLlmModel || "qwen2.5:3b"

  const validateWorkspaceName = (name: string) =>
    hasDuplicateName(
      workspaces.filter((w) => w.id !== currentWs?.id).map((w) => w.name),
      name,
    )
      ? "Đã có không gian cùng tên."
      : null

  return (
    <>
      <header className="flex h-13 shrink-0 items-center justify-between gap-3 border-b border-slate-200/80 bg-white px-3 md:px-5">
        {/* Left: Mobile Menu + Breadcrumb quay lại Dashboard + Tên Workspace & Trạng thái đồng bộ */}
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0 md:hidden"
            aria-label="Mở menu điều hướng"
            onClick={() => setMobile(true)}
          >
            <Menu className="h-4 w-4" />
          </Button>

          {/* Breadcrumb quay lại Dashboard */}
          <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-[13px]">
            <Link
              to="/hub"
              className="group inline-flex items-center gap-1.5 rounded-lg px-2 py-1 font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
            >
              <ArrowLeft className="h-3.5 w-3.5 text-[#2563EB] transition-transform group-hover:-translate-x-0.5" />
              <span className="font-sans font-bold tracking-tight text-slate-900">
                motivo<span className="text-[#2563EB]">.</span>
              </span>
              <span className="hidden text-xs text-slate-500 sm:inline">Dashboard</span>
            </Link>

            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-300" />

            {/* Chọn / Hiển thị Tên Workspace hiện tại */}
            <DropdownMenu
              align="start"
              trigger={
                <button
                  type="button"
                  className="inline-flex max-w-[220px] items-center gap-1.5 rounded-lg px-2 py-1 text-left font-semibold text-slate-900 transition-colors hover:bg-slate-100 sm:max-w-[320px]"
                  title="Chuyển nhanh Workspace"
                >
                  <span className="truncate">{currentWs?.name ?? "Workspace"}</span>
                  <ChevronDown className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                </button>
              }
            >
              <DropdownMenuLabel>Chuyển đổi Workspace</DropdownMenuLabel>
              {workspaces.map((w) => {
                const isSelected = w.id === currentWs?.id
                return (
                  <DropdownMenuItem
                    key={w.id}
                    icon={
                      isSelected ? (
                        <Check className="h-3.5 w-3.5 text-[#2563EB]" />
                      ) : (
                        <FolderOpen className="h-3.5 w-3.5 text-slate-400" />
                      )
                    }
                    onClick={() => {
                      setCurrentWorkspace(w.id)
                      navigate("/chat")
                      toast({
                        title: "Đã chuyển Workspace",
                        description: w.name,
                        tone: "info",
                      })
                    }}
                  >
                    <span className={cn(isSelected && "font-semibold text-[#2563EB]")}>
                      {w.name}
                    </span>
                  </DropdownMenuItem>
                )
              })}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                icon={<ArrowLeft className="h-3.5 w-3.5" />}
                onClick={() => navigate("/hub")}
              >
                Quay lại trang Dashboard (Hub)
              </DropdownMenuItem>
            </DropdownMenu>

            {/* Trạng thái đồng bộ Workspace (chấm xanh lá dành riêng cho trạng thái hệ thống) */}
            <div className="hidden items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-[11px] font-medium text-slate-600 md:inline-flex">
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  processingCount > 0 ? "animate-pulse bg-amber-500" : "bg-[#10B981]",
                )}
              />
              <span>
                {processingCount > 0
                  ? `Đang đồng bộ (${processingCount})`
                  : `Đã đồng bộ · ${readyCount} tài liệu`}
              </span>
            </div>
          </nav>
        </div>

        {/* Right: Trạng thái Ollama/LLM + Cài đặt + Menu thao tác Workspace */}
        <div className="flex shrink-0 items-center gap-2">
          {/* Trạng thái Ollama / Local LLM */}
          <Tooltip
            content="Trạng thái mô hình ngôn ngữ & kết nối RAG. Bấm để cấu hình."
            side="bottom"
          >
            <button
              type="button"
              onClick={() => navigate("/settings?section=status")}
              className="hidden items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-600 transition-colors hover:border-[#2563EB]/40 hover:bg-[#EFF6FF] sm:inline-flex"
            >
              <span className="relative flex h-2 w-2">
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[#10B981]" />
              </span>
              <span className="text-[11px] text-slate-500">LLM:</span>
              <span className="font-mono text-[11px] font-semibold text-slate-900">
                {activeModelName}
              </span>
            </button>
          </Tooltip>

          {/* Nút Cài đặt */}
          <Tooltip content="Cài đặt hệ thống & mô hình" side="bottom">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
              aria-label="Cài đặt"
              onClick={() => navigate("/settings")}
            >
              <Settings className="h-4 w-4" />
            </Button>
          </Tooltip>

          {/* Menu thao tác Workspace */}
          <DropdownMenu
            align="end"
            trigger={
              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 border-slate-200 px-2.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
                aria-label="Menu thao tác Workspace"
              >
                <span className="hidden sm:inline">Workspace</span>
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            }
          >
            <DropdownMenuLabel>{currentWs?.name ?? "Thao tác Workspace"}</DropdownMenuLabel>
            <DropdownMenuItem
              icon={<Pencil className="h-3.5 w-3.5" />}
              onClick={() => setEditOpen(true)}
            >
              Đổi tên &amp; mô tả Workspace
            </DropdownMenuItem>
            <DropdownMenuItem
              icon={<FileUp className="h-3.5 w-3.5" />}
              onClick={() => navigate("/documents")}
            >
              Quản lý kho tài liệu đầy đủ
            </DropdownMenuItem>
            <DropdownMenuItem
              icon={<Activity className="h-3.5 w-3.5" />}
              onClick={() => navigate("/settings?section=status")}
            >
              Kiểm tra trạng thái Ollama / RAG
            </DropdownMenuItem>
            <DropdownMenuItem
              icon={theme === "light" ? <Moon className="h-3.5 w-3.5" /> : <Sun className="h-3.5 w-3.5" />}
              onClick={() => setTheme(theme === "light" ? "dark" : "light")}
            >
              {theme === "light" ? "Chuyển giao diện tối" : "Chuyển giao diện sáng"}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              icon={<ArrowLeft className="h-3.5 w-3.5" />}
              onClick={() => navigate("/hub")}
            >
              Về trang Dashboard (Hub)
            </DropdownMenuItem>
            <DropdownMenuItem
              tone="danger"
              icon={<Trash2 className="h-3.5 w-3.5" />}
              onClick={() => setDeleteOpen(true)}
            >
              Xóa Workspace này
            </DropdownMenuItem>
          </DropdownMenu>
        </div>
      </header>

      {/* Dialog Đổi tên & mô tả Workspace */}
      <NameDialog
        open={editOpen}
        title="Đổi tên &amp; mô tả Workspace"
        initialName={currentWs?.name ?? ""}
        initialDescription={currentWs?.description ?? ""}
        showDescription
        validate={validateWorkspaceName}
        confirmLabel="Lưu thay đổi"
        onClose={() => setEditOpen(false)}
        onSubmit={(name, description) => {
          if (!currentWs) return
          updateWorkspace(currentWs.id, { name, description })
          toast({ title: "Đã cập nhật Workspace", tone: "success" })
          setEditOpen(false)
        }}
      />

      {/* Dialog Xóa Workspace */}
      <ConfirmDialog
        open={deleteOpen}
        title="Xóa Workspace?"
        description={`Bạn có chắc muốn xóa "${currentWs?.name}"? Toàn bộ tài liệu và lịch sử hội thoại trong không gian này sẽ bị xóa.`}
        confirmLabel="Xóa Workspace"
        onClose={() => setDeleteOpen(false)}
        onConfirm={() => {
          if (!currentWs) return
          deleteWorkspace(currentWs.id)
          toast({ title: "Đã xóa Workspace", description: currentWs.name, tone: "info" })
          setDeleteOpen(false)
          navigate("/hub")
        }}
      />
    </>
  )
}
