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
  LogIn,
  LogOut,
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
import { useAuthSession } from "@/hooks/useAuthSession"
import { deleteWorkspaceApi, updateWorkspaceApi } from "@/services/api"
import { logout } from "@/services/auth-service"
import { useAppStore } from "@/store/app-store"
import { cn } from "@/utils/cn"

export function AppHeader() {
  const navigate = useNavigate()
  const { user, authenticated } = useAuthSession()
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
      <header className="flex h-13 shrink-0 items-center justify-between gap-3 border-b border-[#DCECE8] bg-white px-3 md:px-5">
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
              className="group inline-flex items-center gap-1.5 rounded-lg px-2 py-1 font-medium text-[#526B68] transition-colors hover:bg-[#F1F8F6] hover:text-[#0B1716]"
            >
              <ArrowLeft className="h-3.5 w-3.5 text-[#0F766E] transition-transform group-hover:-translate-x-0.5" />
              <span className="font-sans font-bold tracking-tight text-[#0B1716]">
                motivo<span className="text-[#0D9488]">.</span>
              </span>
              <span className="hidden text-xs text-[#647D7A] sm:inline">Dashboard</span>
            </Link>

            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[#B8CECA]" />

            {/* Chọn / Hiển thị Tên Workspace hiện tại */}
            <DropdownMenu
              align="start"
              trigger={
                <button
                  type="button"
                  className="inline-flex max-w-[220px] items-center gap-1.5 rounded-lg px-2 py-1 text-left font-semibold text-[#0B1716] transition-colors hover:bg-[#F1F8F6] sm:max-w-[320px]"
                  title="Chuyển nhanh Workspace"
                >
                  <span className="truncate">{currentWs?.name ?? "Workspace"}</span>
                  <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[#647D7A]" />
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
                        <Check className="h-3.5 w-3.5 text-[#0F766E]" />
                      ) : (
                        <FolderOpen className="h-3.5 w-3.5 text-[#647D7A]" />
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
                    <span className={cn(isSelected && "font-semibold text-[#0F766E]")}>
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

            {/* Trạng thái đồng bộ Workspace */}
            <div className="hidden items-center gap-1.5 rounded-full border border-[#D8EAE6] bg-[#F4FAF8] px-2.5 py-0.5 text-[11px] font-medium text-[#37524F] md:inline-flex">
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
              className="hidden items-center gap-1.5 rounded-full border border-[#D5E6E2] bg-[#F7FAF9] px-2.5 py-1 text-xs text-[#37524F] transition-colors hover:border-[#0F766E]/40 hover:bg-[#EFF7F5] sm:inline-flex"
            >
              <span className="relative flex h-2 w-2">
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[#10B981]" />
              </span>
              <span className="text-[11px] text-[#647D7A]">LLM:</span>
              <span className="font-mono text-[11px] font-semibold text-[#0B1716]">
                {activeModelName}
              </span>
            </button>
          </Tooltip>

          {/* Tài khoản: đăng nhập hoặc đăng xuất */}
          <Tooltip
            content={authenticated ? `Đang đăng nhập: ${user?.email ?? ""}` : "Đăng nhập để dùng backend"}
            side="bottom"
          >
            {authenticated ? (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 gap-1.5 px-2 text-xs text-[#526B68] hover:bg-[#F1F8F6] hover:text-[#0B1716]"
                onClick={() => {
                  logout()
                  navigate("/login")
                }}
                aria-label="Đăng xuất"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span className="hidden lg:inline">Đăng xuất</span>
              </Button>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 gap-1.5 px-2 text-xs text-[#0F766E] hover:bg-[#F1F8F6]"
                onClick={() => navigate("/login")}
                aria-label="Đăng nhập"
              >
                <LogIn className="h-3.5 w-3.5" />
                <span className="hidden lg:inline">Đăng nhập</span>
              </Button>
            )}
          </Tooltip>

          {/* Nút Cài đặt */}
          <Tooltip content="Cài đặt hệ thống & mô hình" side="bottom">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-[#526B68] hover:bg-[#F1F8F6] hover:text-[#0B1716]"
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
                className="h-8 gap-1.5 border-[#D5E6E2] px-2.5 text-xs font-medium text-[#233D3A] hover:bg-[#F1F8F6]"
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
              Tải lên &amp; quản lý tài liệu
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
        onSubmit={async (name, description) => {
          if (!currentWs) return
          try {
            if (authenticated) await updateWorkspaceApi(currentWs.id, name, description)
            updateWorkspace(currentWs.id, { name, description })
            toast({ title: "Đã cập nhật Workspace", tone: "success" })
            setEditOpen(false)
          } catch (err) {
            toast({
              title: "Không thể cập nhật Workspace",
              description: err instanceof Error ? err.message : "Lỗi kết nối backend",
              tone: "error",
            })
          }
        }}
      />

      {/* Dialog Xóa Workspace */}
      <ConfirmDialog
        open={deleteOpen}
        title="Xóa Workspace?"
        description={`Bạn có chắc muốn xóa "${currentWs?.name}"? Toàn bộ tài liệu và lịch sử hội thoại trong không gian này sẽ bị xóa.`}
        confirmLabel="Xóa Workspace"
        onClose={() => setDeleteOpen(false)}
        onConfirm={async () => {
          if (!currentWs) return
          if (currentWs.id === "default") {
            toast({ title: "Không thể xóa workspace mặc định", tone: "error" })
            setDeleteOpen(false)
            return
          }
          try {
            if (authenticated) await deleteWorkspaceApi(currentWs.id)
            deleteWorkspace(currentWs.id)
            toast({ title: "Đã xóa Workspace", description: currentWs.name, tone: "info" })
            setDeleteOpen(false)
            navigate("/hub")
          } catch (err) {
            toast({
              title: "Không thể xóa Workspace",
              description: err instanceof Error ? err.message : "Lỗi kết nối backend",
              tone: "error",
            })
          }
        }}
      />
    </>
  )
}
