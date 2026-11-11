import { useMemo } from "react"
import { Link, useNavigate } from "react-router-dom"
import {
  ArrowLeft,
  ChevronRight,
  LogIn,
  LogOut,
  Menu,
} from "lucide-react"
import { InlineEdit } from "@/components/common/InlineEdit"
import { Button, Tooltip } from "@/components/ui"
import { hasDuplicateName } from "@/features/workspaces/workspace-utils"
import { useAuthSession } from "@/hooks/useAuthSession"
import { updateWorkspaceApi } from "@/services/api"
import { logout } from "@/services/auth-service"
import { useAppStore } from "@/store/app-store"
import { cn } from "@/utils/cn"

export function AppHeader() {
  const navigate = useNavigate()
  const { user, authenticated } = useAuthSession()
  const setMobile = useAppStore((s) => s.setMobileNavOpen)
  const status = useAppStore((s) => s.status)
  const localLlmModel = useAppStore((s) => s.localLlmModel)

  const workspaces = useAppStore((s) => s.workspaces)
  const documents = useAppStore((s) => s.documents)
  const currentWorkspaceId = useAppStore((s) => s.currentWorkspaceId)
  const updateWorkspace = useAppStore((s) => s.updateWorkspace)
  const toast = useAppStore((s) => s.toast)

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
    <header className="flex h-13 shrink-0 items-center justify-between gap-3 border-b border-[#D4E2DF] bg-white px-4 md:px-5">
      {/* Left: Mobile Menu + Breadcrumb quay lại Dashboard + Tên Workspace & Trạng thái đồng bộ */}
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0 md:hidden"
          aria-label="Mở menu điều hướng"
          onClick={() => setMobile(true)}
        >
          <Menu className="h-4 w-4 text-[#172B29]" />
        </Button>

        <nav aria-label="Breadcrumb" className="flex min-w-0 flex-1 items-center gap-2 text-[13px]">
          <Link
            to="/hub"
            className="group relative inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1 font-medium text-[#647C79] transition-all hover:bg-[#F0F5F4] hover:text-[#172B29]"
            title="Quay lại Dashboard"
          >
            <ArrowLeft className="h-3.5 w-3.5 text-[#647C79] transition-transform duration-200 group-hover:-translate-x-1 group-hover:text-[#087F73]" />
            <div className="relative flex h-5 items-center overflow-hidden">
              <span className="font-sans font-bold tracking-tight text-[#172B29] transition-all duration-200 ease-out group-hover:-translate-y-full group-hover:opacity-0">
                motivo<span className="text-[#087F73]">.</span>
              </span>
              <span className="absolute inset-0 flex items-center font-sans text-xs font-semibold text-[#087F73] translate-y-full opacity-0 transition-all duration-200 ease-out group-hover:translate-y-0 group-hover:opacity-100">
                Back
              </span>
            </div>
          </Link>

          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[#B6C8C4]" />

          {/* Tên Workspace hiện tại: Hiển thị đầy đủ, không bị chèn ép chữ */}
          <div className="flex shrink-0 items-center max-w-[220px] sm:max-w-sm md:max-w-md lg:max-w-lg">
            <InlineEdit
              value={currentWs?.name ?? "Workspace"}
              ariaLabel="Tên Workspace"
              validate={validateWorkspaceName}
              onSave={async (next) => {
                if (!currentWs || next === currentWs.name) return
                try {
                  if (authenticated) await updateWorkspaceApi(currentWs.id, next, currentWs.description)
                  updateWorkspace(currentWs.id, { name: next })
                  toast({ title: "Đã đổi tên Workspace", description: next, tone: "success" })
                } catch (err) {
                  toast({
                    title: "Không thể cập nhật Workspace",
                    description: err instanceof Error ? err.message : "Lỗi kết nối backend",
                    tone: "error",
                  })
                }
              }}
              className="truncate text-[13px] font-semibold text-[#172B29] hover:bg-[#F0F5F4] px-1.5 py-0.5 rounded-md transition-colors"
              inputClassName="h-7 text-xs font-semibold text-[#172B29]"
            />
          </div>

          {/* Trạng thái đồng bộ gọn gàng */}
          <div className="hidden shrink-0 items-center gap-1.5 rounded-full border border-[#D4E2DF] bg-[#F5F8F7] px-2.5 py-0.5 text-[11px] font-medium text-[#647C79] sm:inline-flex">
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                processingCount > 0 ? "animate-pulse bg-amber-500" : "bg-[#087F73]",
              )}
            />
            <span>
              {processingCount > 0
                ? `Đang đồng bộ (${processingCount})`
                : `${readyCount} tài liệu`}
            </span>
          </div>
        </nav>
      </div>

      {/* Right: Trạng thái Ollama/LLM + Tài khoản (Đã xóa 2 icon Cài đặt và Menu MoreHorizontal) */}
      <div className="flex shrink-0 items-center gap-2">
        <Tooltip content="Trạng thái mô hình LLM. Bấm để cấu hình." side="bottom">
          <button
            type="button"
            onClick={() => navigate("/settings?section=status")}
            className="hidden items-center gap-1.5 rounded-lg border border-[#D4E2DF] bg-[#F5F8F7] px-2.5 py-1 text-xs text-[#647C79] transition-colors hover:border-[#087F73] hover:text-[#172B29] sm:inline-flex"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-[#087F73]" />
            <span className="font-mono text-[11px] font-semibold text-[#172B29]">
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
      </div>
    </header>
  )
}
