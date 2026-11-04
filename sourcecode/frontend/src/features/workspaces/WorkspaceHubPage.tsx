import { useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  Activity,
  ArrowRight,
  ArrowUpDown,
  FolderKanban,
  Layers,
  LogOut,
  MessageSquare,
  Moon,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Settings,
  Sliders,
  Sun,
  Trash2,
} from "lucide-react"
import { ConfirmDialog, NameDialog } from "@/components/common/NameDialog"
import {
  Button,
  Dialog,
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  FormField,
  Input,
} from "@/components/ui"
import { useSystemStatus } from "@/hooks/useSystemStatus"
import { useAuthSession } from "@/hooks/useAuthSession"
import { createWorkspaceApi, deleteWorkspaceApi, updateWorkspaceApi } from "@/services/api"
import { logout } from "@/services/auth-service"
import { useAppStore } from "@/store/app-store"
import { formatBytes, greeting, relativeTime } from "@/utils/format"
import { hasDuplicateName } from "@/features/workspaces/workspace-utils"
import type { Workspace } from "@/types"
import { cn } from "@/utils/cn"

type SortOption = "updated" | "name" | "documents"

/* ============================================================================
   BỘ ICON SVG TỐI GIẢN, CHUYÊN NGHIỆP (STROKE 1.65PX CHUẨN EDITORIAL / MOTIVO)
============================================================================ */

function IconStatWorkspace() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4.5 w-4.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7.5" height="7.5" rx="2" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="2" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="2" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="2" />
    </svg>
  )
}

function IconStatDocuments() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4.5 w-4.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.5 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6.5L14.5 2Z" />
      <path d="M14 2v5h5" />
      <path d="M9 13h6" />
      <path d="M9 17h4" />
    </svg>
  )
}

function IconStatChunks() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4.5 w-4.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <path d="m12 3 8.5 4.75L12 12.5 3.5 7.75 12 3Z" />
      <path d="m3.5 12.25 8.5 4.75 8.5-4.75" />
      <path d="m3.5 16.75 8.5 4.75 8.5-4.75" />
    </svg>
  )
}

function IconStatStorage() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4.5 w-4.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5" />
      <path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3" />
    </svg>
  )
}

/**
 * Icon chuyên nghiệp cho từng thẻ Workspace (nét mảnh, hình học hiện đại)
 */
function WorkspaceGlyph({ category, index }: { category?: string; index: number }) {
  const key = category || ["Dự án", "Kỹ thuật", "Nghiên cứu", "Đại học"][index % 4]
  switch (key) {
    case "Kỹ thuật":
      return (
        <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="16 18 22 12 16 6" />
          <polyline points="8 6 2 12 8 18" />
          <line x1="13.5" y1="4" x2="10.5" y2="20" />
        </svg>
      )
    case "Nghiên cứu":
      return (
        <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
          <path d="M8.5 11h5" />
          <path d="M11 8.5v5" />
        </svg>
      )
    case "Ngoại ngữ":
      return (
        <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a2.5 2.5 0 0 1 0-5H20" />
          <path d="M8.5 7h7" />
          <path d="M8.5 11h4" />
        </svg>
      )
    case "Đại học":
      return (
        <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
          <path d="M2 6a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H4a2 2 0 0 1-2-2V6Z" />
          <path d="M22 6a2 2 0 0 0-2-2h-5a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h5a2 2 0 0 0 2-2V6Z" />
        </svg>
      )
    default:
      return (
        <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h4.17a2 2 0 0 1 1.41.59l1.34 1.34a2 2 0 0 0 1.41.59H18.5A2.5 2.5 0 0 1 21 10v7.5a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5v-10Z" />
        </svg>
      )
  }
}

export function WorkspaceHubPage() {
  const navigate = useNavigate()
  const searchInputRef = useRef<HTMLInputElement>(null)
  useSystemStatus()
  const { user, authenticated } = useAuthSession()

  const workspaces = useAppStore((s) => s.workspaces)
  const documents = useAppStore((s) => s.documents)
  const conversations = useAppStore((s) => s.conversations)
  const setCurrent = useAppStore((s) => s.setCurrentWorkspace)
  const createWorkspace = useAppStore((s) => s.createWorkspace)
  const updateWorkspace = useAppStore((s) => s.updateWorkspace)
  const deleteWorkspace = useAppStore((s) => s.deleteWorkspace)
  const mergeWorkspaces = useAppStore((s) => s.mergeWorkspacesFromBackend)
  const createConversation = useAppStore((s) => s.createConversation)
  const status = useAppStore((s) => s.status)
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const localLlmModel = useAppStore((s) => s.localLlmModel)
  const toast = useAppStore((s) => s.toast)

  // Search & Sort
  const [searchQuery, setSearchQuery] = useState("")
  const [sortOption, setSortOption] = useState<SortOption>("updated")

  // Dialogs
  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Workspace | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Workspace | null>(null)

  // Calculate Metrics
  const totalDocs = documents.length

  const totalChunks = useMemo(
    () => documents.reduce((acc, d) => acc + (d.totalChunks || 0), 0),
    [documents],
  )
  const formattedChunks =
    totalChunks >= 1000 ? `${(totalChunks / 1000).toFixed(1)}k` : `${totalChunks}`

  const totalSizeBytes = useMemo(
    () => documents.reduce((acc, d) => acc + (d.fileSize || 0), 0),
    [documents],
  )
  const totalSizeDisplay = formatBytes(totalSizeBytes)

  // Filtered and Sorted Workspaces
  const filteredWorkspaces = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    const list = workspaces.filter((w) => {
      if (q) {
        const matchName = w.name.toLowerCase().includes(q)
        const matchDesc = (w.description || "").toLowerCase().includes(q)
        if (!matchName && !matchDesc) return false
      }
      return true
    })

    return [...list].sort((a, b) => {
      if (sortOption === "name") {
        return a.name.localeCompare(b.name, "vi")
      }
      if (sortOption === "documents") {
        const aDocs = documents.filter((d) => d.workspaceId === a.id).length
        const bDocs = documents.filter((d) => d.workspaceId === b.id).length
        return bDocs - aDocs
      }
      return b.updatedAt.localeCompare(a.updatedAt)
    })
  }, [workspaces, searchQuery, sortOption, documents])

  // Actions: Mở thẳng Workspace Studio (trung tâm là Chat AI)
  const handleEnterWorkspace = (w: Workspace, forceNewChat = false) => {
    setCurrent(w.id)
    toast({
      title: "Đã mở Workspace Studio",
      description: w.name,
      tone: "info",
    })
    const convInWs = conversations.find((c) => c.workspaceId === w.id)
    if (convInWs && !forceNewChat) {
      navigate(`/chat/${convInWs.id}`)
    } else if (forceNewChat && !convInWs) {
      const newConv = createConversation(w.id)
      navigate(`/chat/${newConv.id}`)
    } else {
      navigate("/chat")
    }
  }

  const validateWorkspaceName = (exceptId?: string) => (name: string) =>
    hasDuplicateName(
      workspaces.filter((w) => w.id !== exceptId).map((w) => w.name),
      name,
    )
      ? "Đã có không gian cùng tên."
      : null

  return (
    <div className="flex min-h-screen flex-col bg-[#F1F5F4] text-[#0B1716] antialiased selection:bg-[#BCECE0] selection:text-[#0B1716]">
      {/* =====================================================================
          PHẦN 1: THANH DASHBOARD (TOP HEADER)
      ===================================================================== */}
      <header
        className="sticky top-0 z-50 border-b border-[#D5E6E2] bg-white/90 backdrop-blur-md"
        data-purpose="dashboard-top-bar"
      >
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          {/* Brand Logo kiểu Motivo */}
          <button
            type="button"
            onClick={() => navigate("/hub")}
            className="group flex items-center gap-2.5 text-left"
            aria-label="Trang chủ Workspace Hub"
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#0F766E] text-white shadow-xs transition-transform duration-200 group-hover:scale-105">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                className="h-4.5 w-4.5"
                aria-hidden="true"
              >
                <path
                  d="M12 2.5v19M3.8 7.25l16.4 9.5M20.2 7.25l-16.4 9.5"
                  stroke="currentColor"
                  strokeWidth="2.6"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <span className="font-sans text-xl font-bold tracking-tight text-[#0B1716]">
              motivo<span className="text-[#0D9488]">.</span>
            </span>
          </button>

          {/* Right Controls: Ollama Status + New Workspace CTA + User Profile Dropdown */}
          <div className="flex items-center gap-3">
            {/* Trạng thái AI Local */}
            <div className="hidden items-center gap-2 rounded-full border border-[#CBE4DF] bg-[#F4FAF9] px-3 py-1.5 text-xs font-medium text-[#37524F] sm:flex">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[#10B981]" />
              </span>
              <span className="text-[11px] text-[#5C7875]">Ollama:</span>
              <span className="font-mono text-[11px] font-semibold text-[#0B1716]">
                {status.ollamaModels[0] || localLlmModel || "Llama-3.1 8B"}
              </span>
            </div>

            {/* Nút tạo Workspace mới kiểu pill đen đặc trưng của Motivo */}
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="group inline-flex items-center gap-2.5 rounded-full bg-[#0B1315] py-1.5 pr-2 pl-4 text-xs font-semibold text-white shadow-sm transition-all duration-200 hover:bg-[#0F766E]"
            >
              <span>Workspace mới</span>
              <span className="flex h-5 w-5 items-center justify-center rounded-full border border-white/25 transition-transform group-hover:rotate-90">
                <Plus className="h-3 w-3" />
              </span>
            </button>

            {/* Droplist Hồ sơ người dùng (Tích hợp Cài đặt hệ thống) */}
            <DropdownMenu
              align="end"
              trigger={
                <button
                  type="button"
                  className="flex items-center gap-2 rounded-full border border-[#CBE4DF] bg-white p-1 pr-3 text-left shadow-2xs transition-colors hover:border-[#0D9488]/50 hover:bg-[#F4FAF9]"
                  title="Hồ sơ & Cài đặt hệ thống"
                >
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[#0F766E] text-xs font-bold text-white">
                    {(user?.name || user?.email || "KH").slice(0, 2).toUpperCase()}
                  </div>
                  <span className="hidden max-w-[140px] truncate text-xs font-semibold text-[#0B1716] sm:inline">
                    {user?.name || (authenticated ? "Tài khoản" : "Khách")}
                  </span>
                </button>
              }
            >
              <DropdownMenuLabel>
                {authenticated
                  ? `${user?.name || user?.email} · Đã đăng nhập`
                  : "Chưa đăng nhập · Dữ liệu mô phỏng"}
              </DropdownMenuLabel>
              {authenticated ? (
                <DropdownMenuItem
                  icon={<Settings className="h-3.5 w-3.5" />}
                  onClick={() => navigate("/settings")}
                >
                  Cài đặt tài khoản
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem
                  icon={<Settings className="h-3.5 w-3.5" />}
                  onClick={() => navigate("/login")}
                >
                  Đăng nhập / Đăng ký
                </DropdownMenuItem>
              )}

              <DropdownMenuSeparator />
              <DropdownMenuLabel>Cài đặt hệ thống</DropdownMenuLabel>
              <DropdownMenuItem
                icon={<Activity className="h-3.5 w-3.5" />}
                onClick={() => navigate("/settings?section=status")}
              >
                Trạng thái hệ thống &amp; AI
              </DropdownMenuItem>
              <DropdownMenuItem
                icon={<Sliders className="h-3.5 w-3.5" />}
                onClick={() => navigate("/settings")}
              >
                Cấu hình mô hình LLM &amp; RAG
              </DropdownMenuItem>
              <DropdownMenuItem
                icon={<Layers className="h-3.5 w-3.5" />}
                onClick={() => navigate("/design-system")}
              >
                Giao diện &amp; Design System
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                icon={
                  theme === "dark" ? (
                    <Sun className="h-3.5 w-3.5" />
                  ) : (
                    <Moon className="h-3.5 w-3.5" />
                  )
                }
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              >
                {theme === "dark" ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"}
              </DropdownMenuItem>
              {authenticated ? (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    icon={<LogOut className="h-3.5 w-3.5" />}
                    onClick={() => {
                      logout()
                      navigate("/login")
                    }}
                  >
                    Đăng xuất
                  </DropdownMenuItem>
                </>
              ) : null}
            </DropdownMenu>
          </div>
        </div>
      </header>

      {/* =====================================================================
          PHẦN 2: KHUNG CHÀO MỪNG (TRÁI) & 4 Ô THỐNG KÊ HÌNH VUÔNG 2x2 (PHẢI)
          Giữ nguyên chiều cao vùng nền như cũ, tăng nhẹ kích thước 4 ô thống kê
      ===================================================================== */}
      <section
        className="relative flex min-h-[212px] items-center overflow-hidden border-b border-[#D2E5E1] bg-gradient-to-br from-[#DCF2EE] via-[#E8F6F3] to-[#DFF0FA] py-8"
        data-purpose="hero-and-metrics-section"
      >
        {/* Hiệu ứng ánh sáng nền kiểu Motivo */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-20 left-1/3 h-72 w-72 rounded-full bg-[#99F6E4]/40 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute right-10 bottom-0 h-64 w-64 rounded-full bg-[#BAE6FD]/45 blur-3xl"
        />

        <div className="relative mx-auto w-full max-w-6xl px-6">
          <div className="grid grid-cols-1 items-center gap-8 lg:grid-cols-12">
            {/* Bên trái: Lời chào với Tên nổi bật + Slogan ngắn gọn */}
            <div className="space-y-3.5 lg:col-span-7">
              <h1 className="font-editorial-serif text-4xl leading-[1.15] font-medium tracking-tight text-[#0B1716] sm:text-5xl">
                {greeting()},{" "}
                <span className="bg-gradient-to-r from-[#0F766E] via-[#0D9488] to-[#0284C7] bg-clip-text font-semibold italic text-transparent underline decoration-[#0D9488]/35 decoration-2 underline-offset-8">
                  {user?.name || "bạn"}
                </span>{" "}
                👋
              </h1>

              <p className="max-w-lg text-base font-medium leading-relaxed text-[#2C4A47] sm:text-lg">
                Không gian tri thức tách biệt — Tập trung tối đa, hiệu quả vượt trội.
              </p>
            </div>

            {/* Bên phải: 4 ô thống kê 2x2 được tăng kích thước vừa vặn, cân đối */}
            <div className="grid w-full max-w-[376px] grid-cols-2 gap-3 lg:col-span-5 lg:ml-auto">
              {/* Ô 1: Workspace */}
              <div className="flex items-center gap-3.5 rounded-2xl border border-white/95 bg-white/92 px-4 py-3 shadow-[0_6px_20px_-6px_rgba(11,35,32,0.06)] backdrop-blur-xs">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#DFF5F0] text-[#0F766E]">
                  <IconStatWorkspace />
                </div>
                <div className="min-w-0">
                  <div className="font-sans text-lg leading-tight font-bold text-[#0B1716] sm:text-[19px]">
                    {workspaces.length}
                  </div>
                  <div className="mt-0.5 truncate text-xs font-medium text-[#5C7875]">
                    Workspace
                  </div>
                </div>
              </div>

              {/* Ô 2: Tài liệu */}
              <div className="flex items-center gap-3.5 rounded-2xl border border-white/95 bg-white/92 px-4 py-3 shadow-[0_6px_20px_-6px_rgba(11,35,32,0.06)] backdrop-blur-xs">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#E0F2FE] text-[#0284C7]">
                  <IconStatDocuments />
                </div>
                <div className="min-w-0">
                  <div className="font-sans text-lg leading-tight font-bold text-[#0B1716] sm:text-[19px]">
                    {totalDocs}
                  </div>
                  <div className="mt-0.5 truncate text-xs font-medium text-[#5C7875]">
                    Tài liệu
                  </div>
                </div>
              </div>

              {/* Ô 3: Chunks */}
              <div className="flex items-center gap-3.5 rounded-2xl border border-white/95 bg-white/92 px-4 py-3 shadow-[0_6px_20px_-6px_rgba(11,35,32,0.06)] backdrop-blur-xs">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#EEF2FF] text-[#4F46E5]">
                  <IconStatChunks />
                </div>
                <div className="min-w-0">
                  <div className="font-sans text-lg leading-tight font-bold text-[#0B1716] sm:text-[19px]">
                    {formattedChunks}
                  </div>
                  <div className="mt-0.5 truncate text-xs font-medium text-[#5C7875]">
                    Chunks
                  </div>
                </div>
              </div>

              {/* Ô 4: Bộ nhớ */}
              <div className="flex items-center gap-3.5 rounded-2xl border border-white/95 bg-white/92 px-4 py-3 shadow-[0_6px_20px_-6px_rgba(11,35,32,0.06)] backdrop-blur-xs">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#CCFBF1] text-[#0F766E]">
                  <IconStatStorage />
                </div>
                <div className="min-w-0">
                  <div className="truncate font-sans text-lg leading-tight font-bold text-[#0B1716] sm:text-[19px]">
                    {totalSizeDisplay}
                  </div>
                  <div className="mt-0.5 truncate text-xs font-medium text-[#5C7875]">
                    Bộ nhớ
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =====================================================================
          PHẦN 3: CÁC WORKSPACE GẦN ĐÂY (RECENT WORKSPACES SECTION)
          Thiết kế chuyên nghiệp chuẩn SaaS (Linear / Motivo):
          - Icon vector nét mảnh tinh tế, không dùng khối màu AI lòe loẹt
          - Khoảng cách chữ (Typography & Spacing) chặt chẽ, dễ đọc
      ===================================================================== */}
      <main
        className="mx-auto w-full max-w-6xl flex-1 space-y-6 px-6 py-10"
        data-purpose="recent-workspaces-section"
      >
        {/* Header của Phần 3 + Thanh Tìm kiếm & Sắp xếp */}
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div className="flex items-center gap-3">
            <h2 className="font-editorial-serif text-2xl font-medium text-[#0B1716] sm:text-[28px]">
              Không gian làm việc gần đây
            </h2>
            <span className="rounded-full bg-[#DFF5F0] px-2.5 py-0.5 text-xs font-bold text-[#0F766E]">
              {filteredWorkspaces.length}
            </span>
          </div>

          {/* Thanh Tìm kiếm & Nút Sắp xếp */}
          <div className="flex flex-wrap items-center gap-3 sm:flex-nowrap">
            <div className="relative flex w-full items-center gap-2 rounded-full border border-[#C8DED9] bg-white px-4 py-2 shadow-2xs transition-all focus-within:border-[#0F766E] focus-within:ring-2 focus-within:ring-[#0F766E]/15 sm:w-72">
              <Search className="h-4 w-4 shrink-0 text-[#647D7A]" />
              <input
                ref={searchInputRef}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full border-none bg-transparent font-sans text-xs text-[#0B1716] placeholder-[#7A9490] outline-none focus:ring-0"
                placeholder="Tìm kiếm Workspace..."
                type="text"
              />
            </div>

            <DropdownMenu
              align="end"
              trigger={
                <button
                  type="button"
                  className="inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-full border border-[#C8DED9] bg-white px-3.5 py-2 text-xs font-semibold text-[#233D3A] shadow-2xs transition hover:border-[#0F766E] hover:bg-[#F4FAF9]"
                >
                  <ArrowUpDown className="h-3.5 w-3.5 text-[#0F766E]" />
                  <span>
                    {sortOption === "updated"
                      ? "Cập nhật gần nhất"
                      : sortOption === "name"
                        ? "Tên A-Z"
                        : "Số tài liệu"}
                  </span>
                </button>
              }
            >
              <DropdownMenuItem onClick={() => setSortOption("updated")}>
                Cập nhật gần nhất
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setSortOption("name")}>
                Tên A-Z
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setSortOption("documents")}>
                Nhiều tài liệu nhất
              </DropdownMenuItem>
            </DropdownMenu>
          </div>
        </div>

        {/* Lưới thẻ Workspace chuyên nghiệp */}
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
          {filteredWorkspaces.map((w, idx) => {
            const wsDocs = documents.filter((d) => d.workspaceId === w.id)
            const wsConvs = conversations.filter((c) => c.workspaceId === w.id)
            const docCount = wsDocs.length

            return (
              <article
                key={w.id}
                onClick={() => handleEnterWorkspace(w, false)}
                className={cn(
                  "group flex cursor-pointer flex-col justify-between rounded-2xl border border-[#CEDFD9] bg-white p-5",
                  "shadow-[0_4px_20px_-4px_rgba(11,25,23,0.06),0_1px_3px_rgba(11,25,23,0.03)]",
                  "transition-all duration-200 hover:-translate-y-1 hover:border-[#0F766E]/60 hover:shadow-[0_16px_36px_-10px_rgba(15,118,110,0.16)]",
                )}
              >
                <div>
                  {/* Hàng trên: Icon nét mảnh tinh tế + Danh mục/Thời gian + Menu 3 chấm */}
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[#D5E8E3] bg-[#F2F9F7] text-[#0F6E66] transition-colors duration-200 group-hover:border-[#0B1315] group-hover:bg-[#0B1315] group-hover:text-white">
                        <WorkspaceGlyph category={w.category} index={idx} />
                      </div>
                      <div className="flex flex-col">
                        <span className="text-[11px] font-semibold tracking-wide text-[#0F766E]">
                          {w.category || "Cá nhân"}
                        </span>
                        <span className="text-[11px] text-[#6E8582]">
                          Cập nhật {relativeTime(w.updatedAt)}
                        </span>
                      </div>
                    </div>

                    <div onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu
                        align="end"
                        trigger={
                          <button
                            type="button"
                            className="rounded-lg p-1.5 text-[#7A9490] transition hover:bg-[#EFF6F5] hover:text-[#0B1716]"
                            title="Tùy chọn"
                            aria-label={`Tùy chọn cho ${w.name}`}
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </button>
                        }
                      >
                        <DropdownMenuItem
                          icon={<FolderKanban className="h-3.5 w-3.5" />}
                          onClick={() => handleEnterWorkspace(w, false)}
                        >
                          Mở Workspace
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          icon={<MessageSquare className="h-3.5 w-3.5" />}
                          onClick={() => handleEnterWorkspace(w, true)}
                        >
                          Hỏi đáp AI trong workspace
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          icon={<Pencil className="h-3.5 w-3.5" />}
                          onClick={() => setEditTarget(w)}
                        >
                          Đổi tên &amp; mô tả
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          tone="danger"
                          icon={<Trash2 className="h-3.5 w-3.5" />}
                          onClick={() => setDeleteTarget(w)}
                        >
                          Xóa workspace
                        </DropdownMenuItem>
                      </DropdownMenu>
                    </div>
                  </div>

                  {/* Khối Tiêu đề & Mô tả với khoảng cách chuẩn xác */}
                  <div className="mt-4">
                    <h3 className="text-[16px] leading-snug font-bold tracking-[-0.01em] text-[#0B1716] transition-colors group-hover:text-[#0F766E]">
                      {w.name}
                    </h3>
                    <p className="mt-1.5 line-clamp-2 text-[13px] leading-[1.55] text-[#526B68]">
                      {w.description || "Không gian làm việc với tài liệu và trợ lý RAG cá nhân."}
                    </p>
                  </div>
                </div>

                {/* Chân thẻ: Thông số gọn sạch bên trái + Nút "Mở" bên phải */}
                <div className="mt-5 flex items-center justify-between border-t border-[#EBF2F0] pt-3.5">
                  <div className="flex items-center gap-2 text-xs font-medium text-[#526B68]">
                    <span>{docCount} tài liệu</span>
                    <span className="text-[#CBDAD7]">&bull;</span>
                    <span>{wsConvs.length} hội thoại</span>
                  </div>

                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleEnterWorkspace(w, false)
                    }}
                    className="group/btn inline-flex items-center gap-1.5 rounded-full bg-[#0B1315] px-3.5 py-1.5 text-xs font-semibold text-white transition-all duration-200 hover:bg-[#0F766E]"
                  >
                    <span>Mở</span>
                    <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover/btn:translate-x-0.5" />
                  </button>
                </div>
              </article>
            )
          })}

          {/* Thẻ Tạo Workspace mới */}
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="group flex min-h-[210px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed border-[#B2D0CA] bg-white/65 p-5 text-center transition-all duration-200 hover:-translate-y-1 hover:border-[#0F766E] hover:bg-white hover:shadow-md"
          >
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl border border-[#D5E8E3] bg-[#F2F9F7] text-[#0F6E66] transition-colors duration-200 group-hover:border-[#0B1315] group-hover:bg-[#0B1315] group-hover:text-white">
              <Plus className="h-5 w-5" />
            </div>
            <h3 className="text-[15px] font-bold text-[#0B1716]">
              Tạo Workspace mới
            </h3>
            <p className="mt-1 max-w-[220px] text-[12px] leading-relaxed text-[#526B68]">
              Khởi tạo không gian độc lập cho môn học hoặc dự án mới.
            </p>
          </button>
        </div>
      </main>

      {/* Footer tối giản kiểu Motivo */}
      <footer className="mt-auto border-t border-[#D5E6E2] bg-white py-6">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 text-xs text-[#647D7A] sm:flex-row">
          <div className="flex items-center gap-2">
            <span className="font-sans font-bold text-[#0B1716]">
              motivo<span className="text-[#0D9488]">.</span>
            </span>
            <span>— Không gian tri thức AI cá nhân</span>
          </div>
          <span>&copy; 2026 Motivo Workspace. All rights reserved.</span>
        </div>
      </footer>

      {/* Dialog: Create Workspace */}
      <Dialog
        open={createOpen}
        title="Tạo Workspace mới"
        onClose={() => setCreateOpen(false)}
      >
        <form
          onSubmit={async (e) => {
            e.preventDefault()
            const form = e.currentTarget
            const nameInput = form.elements.namedItem("wsName") as HTMLInputElement
            const descInput = form.elements.namedItem("wsDesc") as HTMLTextAreaElement
            const name = nameInput.value.trim()
            if (!name) return

            const duplicate = hasDuplicateName(
              workspaces.map((w) => w.name),
              name,
            )
            if (duplicate) {
              toast({ title: "Đã có Workspace cùng tên", tone: "error" })
              return
            }

            let ws: Workspace
            try {
              if (authenticated) {
                ws = await createWorkspaceApi(name, descInput.value.trim())
                mergeWorkspaces([ws])
              } else {
                ws = createWorkspace(name, descInput.value.trim())
              }
            } catch (err) {
              toast({
                title: "Không thể tạo Workspace",
                description: err instanceof Error ? err.message : "Lỗi kết nối backend",
                tone: "error",
              })
              return
            }
            toast({
              title: "Đã tạo Workspace mới",
              description: ws.name,
              tone: "success",
            })
            setCreateOpen(false)
            handleEnterWorkspace(ws, false)
          }}
          className="space-y-3"
        >
          <FormField label="Tên Workspace">
            <Input
              name="wsName"
              autoFocus
              required
              placeholder="Ví dụ: Đồ án Mạng & An toàn thông tin..."
            />
          </FormField>

          <FormField label="Mô tả">
            <textarea
              name="wsDesc"
              rows={3}
              className="w-full rounded-md border border-line bg-bg p-2 text-xs text-ink placeholder:text-muted focus:border-brand focus:outline-hidden"
              placeholder="Mô tả ngắn gọn về đề tài, tài liệu hoặc mục tiêu nghiên cứu..."
            />
          </FormField>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setCreateOpen(false)}
            >
              Hủy
            </Button>
            <Button type="submit">Tạo không gian</Button>
          </div>
        </form>
      </Dialog>

      {/* Dialog: Edit Workspace */}
      <NameDialog
        open={Boolean(editTarget)}
        title="Đổi tên &amp; mô tả Workspace"
        initialName={editTarget?.name ?? ""}
        initialDescription={editTarget?.description ?? ""}
        showDescription
        validate={validateWorkspaceName(editTarget?.id)}
        onClose={() => setEditTarget(null)}
        confirmLabel="Lưu thay đổi"
        onSubmit={async (name, description) => {
          if (!editTarget) return
          try {
            if (authenticated) await updateWorkspaceApi(editTarget.id, name, description)
            updateWorkspace(editTarget.id, { name, description })
            toast({ title: "Đã cập nhật Workspace", tone: "success" })
          } catch (err) {
            toast({
              title: "Không thể cập nhật Workspace",
              description: err instanceof Error ? err.message : "Lỗi kết nối backend",
              tone: "error",
            })
          }
          setEditTarget(null)
        }}
      />

      {/* Dialog: Delete Workspace */}
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Xóa Workspace"
        description={`Bạn có chắc chắn muốn xóa "${deleteTarget?.name}"? Toàn bộ tài liệu và hội thoại bên trong sẽ bị gỡ bỏ.`}
        confirmLabel="Xóa vĩnh viễn"
        onClose={() => setDeleteTarget(null)}
        onConfirm={async () => {
          if (!deleteTarget) return
          if (deleteTarget.id === "default") {
            toast({ title: "Không thể xóa workspace mặc định", tone: "error" })
            return
          }
          try {
            if (authenticated) await deleteWorkspaceApi(deleteTarget.id)
            deleteWorkspace(deleteTarget.id)
            toast({ title: "Đã xóa Workspace", description: deleteTarget.name, tone: "info" })
          } catch (err) {
            toast({
              title: "Không thể xóa Workspace",
              description: err instanceof Error ? err.message : "Lỗi kết nối backend",
              tone: "error",
            })
          }
          setDeleteTarget(null)
        }}
      />
    </div>
  )
}
