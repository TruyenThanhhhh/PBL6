import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  Activity,
  ArrowRight,
  ArrowUpDown,
  Check,
  FileText,
  FolderKanban,
  Layers,
  Loader2,
  LogOut,
  MessageSquare,
  Moon,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Settings,
  Sliders,
  Sparkles,
  Sun,
  Trash2,
} from "lucide-react"
import { ConfirmDialog, NameDialog } from "@/components/common/NameDialog"
import {
  DropdownMenu,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui"
import { useSystemStatus } from "@/hooks/useSystemStatus"
import { useAuthSession } from "@/hooks/useAuthSession"
import {
  deleteWorkspaceApi,
  generateWorkspaceMetadataApi,
  searchWorkspacesSemanticApi,
  updateWorkspaceApi,
} from "@/services/api"
import { logout } from "@/services/auth-service"
import { useAppStore } from "@/store/app-store"
import { formatBytes, greeting, relativeTime } from "@/utils/format"
import { createQuickWorkspaceFlow, hasDuplicateName } from "@/features/workspaces/workspace-utils"
import type { Workspace } from "@/types"
import { cn } from "@/utils/cn"

type SortOption = "newest" | "oldest" | "name-asc" | "name-desc"

const SORT_LABELS: Record<SortOption, string> = {
  newest: "Mới nhất",
  oldest: "Cũ nhất",
  "name-asc": "Tên A–Z",
  "name-desc": "Tên Z–A",
}

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
  const updateWorkspace = useAppStore((s) => s.updateWorkspace)
  const mergeWorkspaces = useAppStore((s) => s.mergeWorkspacesFromBackend)
  const deleteWorkspace = useAppStore((s) => s.deleteWorkspace)
  const createConversation = useAppStore((s) => s.createConversation)
  const status = useAppStore((s) => s.status)
  const theme = useAppStore((s) => s.theme)
  const setTheme = useAppStore((s) => s.setTheme)
  const localLlmModel = useAppStore((s) => s.localLlmModel)
  const toast = useAppStore((s) => s.toast)

  // Search & Sort
  const [searchQuery, setSearchQuery] = useState("")
  const [sortOption, setSortOption] = useState<SortOption>("newest")
  const [semanticResults, setSemanticResults] = useState<Workspace[] | null>(null)
  const [searchingSemantic, setSearchingSemantic] = useState(false)

  // Quick Create & Dialogs
  const [creatingWs, setCreatingWs] = useState(false)
  const [editTarget, setEditTarget] = useState<Workspace | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Workspace | null>(null)

  useEffect(() => {
    const q = searchQuery.trim()
    if (!q || !authenticated || !status.backendOnline) {
      return
    }

    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setSearchingSemantic(true)
      try {
        const res = await searchWorkspacesSemanticApi(q, controller.signal)
        if (!controller.signal.aborted) {
          setSemanticResults(res.workspaces)
        }
      } catch {
        if (!controller.signal.aborted) {
          setSemanticResults(null)
        }
      } finally {
        if (!controller.signal.aborted) {
          setSearchingSemantic(false)
        }
      }
    }, 280)

    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [searchQuery, authenticated, status.backendOnline])

  const activeSemanticResults =
    searchQuery.trim() && authenticated && status.backendOnline ? semanticResults : null
  const showSearchingSemantic =
    Boolean(searchQuery.trim() && authenticated && status.backendOnline && searchingSemantic)

  // Calculate Metrics
  const totalDocs = useMemo(() => {
    const backendSum = workspaces.reduce((acc, w) => acc + (w.docCount ?? 0), 0)
    const hasBackendCounts = workspaces.some((w) => w.docCount !== undefined)
    return hasBackendCounts ? backendSum : documents.length
  }, [workspaces, documents.length])

  const totalSizeBytes = useMemo(
    () => documents.reduce((acc, d) => acc + (d.fileSize || 0), 0),
    [documents],
  )
  const totalSizeDisplay = formatBytes(totalSizeBytes)
  const [todayLabel] = useState(() =>
    new Date().toLocaleDateString("vi-VN", {
      weekday: "long",
      day: "numeric",
      month: "long",
    }),
  )

  // Filtered and Sorted Workspaces
  const filteredWorkspaces = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (q && activeSemanticResults !== null) {
      return activeSemanticResults
    }

    const list = workspaces.filter((w) => {
      if (q) {
        const matchName = w.name.toLowerCase().includes(q)
        const matchDesc = (w.description || "").toLowerCase().includes(q)
        if (!matchName && !matchDesc) return false
      }
      return true
    })

    return [...list].sort((a, b) => {
      switch (sortOption) {
        case "name-asc":
          return a.name.localeCompare(b.name, "vi")
        case "name-desc":
          return b.name.localeCompare(a.name, "vi")
        case "oldest":
          return a.updatedAt.localeCompare(b.updatedAt)
        default:
          return b.updatedAt.localeCompare(a.updatedAt)
      }
    })
  }, [workspaces, searchQuery, activeSemanticResults, sortOption])

  // Actions: Mở thẳng Workspace Studio (trung tâm là Chat AI)
  const handleEnterWorkspace = (w: Workspace, forceNewChat = false, silent = false) => {
    setCurrent(w.id)
    if (!silent) {
      toast({
        title: "Đã mở Workspace Studio",
        description: w.name,
        tone: "info",
      })
    }
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

  const handleQuickCreateWorkspace = async () => {
    if (creatingWs) return
    setCreatingWs(true)
    try {
      const ws = await createQuickWorkspaceFlow(authenticated)
      handleEnterWorkspace(ws, false, true)
    } catch (err) {
      toast({
        title: "Không thể tạo Workspace",
        description: err instanceof Error ? err.message : "Lỗi kết nối backend",
        tone: "error",
      })
    } finally {
      setCreatingWs(false)
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
    <div className="flex min-h-screen flex-col bg-[#F1F5F4] font-sans text-[#0B1716] antialiased selection:bg-[#BCECE0] selection:text-[#0B1716]">
      {/* =====================================================================
          PHẦN 1: THANH DASHBOARD (TOP HEADER)
      ===================================================================== */}
      <header
        className="sticky top-0 z-50 border-b border-[#D5E6E2] bg-white/90 backdrop-blur-md"
        data-purpose="dashboard-top-bar"
      >
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
          {/* Brand Logo kiểu Motivo */}
          <button
            type="button"
            onClick={() => navigate("/hub")}
            className="group flex shrink-0 items-center gap-2 text-left"
            aria-label="Trang chủ Workspace Hub"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#0F766E] text-white shadow-xs transition-transform duration-200 group-hover:scale-105">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                className="h-4 w-4"
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
            <span className="font-sans text-lg font-bold tracking-tight text-[#0B1716]">
              motivo<span className="text-[#0D9488]">.</span>
            </span>
          </button>

          {/* Right Controls: Ollama Status + New Workspace CTA + User Profile Dropdown */}
          <div className="flex min-w-0 items-center gap-2 sm:gap-2.5">
            {/* Trạng thái AI Local */}
            <div className="hidden h-8 min-w-0 items-center gap-1.5 rounded-full border border-[#CBE4DF] bg-[#F4FAF9] px-3 text-xs text-[#37524F] md:flex">
              <span className="relative flex h-2 w-2 shrink-0">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[#10B981]" />
              </span>
              <span className="font-medium text-[#5C7875]">Ollama:</span>
              <span className="max-w-[140px] truncate font-semibold text-[#0B1716]">
                {status.ollamaModels[0] || localLlmModel || "Llama-3.1 8B"}
              </span>
            </div>

            {/* Nút tạo Workspace mới kiểu pill đen đặc trưng của Motivo */}
            <button
              type="button"
              disabled={creatingWs}
              onClick={() => void handleQuickCreateWorkspace()}
              aria-label="Tạo Workspace mới"
              className="group inline-flex h-8 shrink-0 items-center gap-2 rounded-full bg-[#0B1315] pr-1.5 pl-1.5 text-xs font-semibold text-white shadow-sm transition-colors duration-200 hover:bg-[#0F766E] disabled:opacity-60 sm:pl-3.5"
            >
              <span className="hidden sm:inline">{creatingWs ? "Đang tạo..." : "Workspace mới"}</span>
              <span className="flex h-5 w-5 items-center justify-center rounded-full border border-white/25 transition-transform group-hover:rotate-90">
                {creatingWs ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
              </span>
            </button>

            {/* Droplist Hồ sơ người dùng (Tích hợp Cài đặt hệ thống) */}
            <DropdownMenu
              align="end"
              trigger={
                <button
                  type="button"
                  className="flex h-8 items-center gap-2 rounded-full border border-[#CBE4DF] bg-white p-0.5 text-left shadow-2xs transition-colors hover:border-[#0D9488]/50 hover:bg-[#F4FAF9] sm:pr-3"
                  title="Hồ sơ & Cài đặt hệ thống"
                >
                  <div className="flex h-6.5 w-6.5 items-center justify-center rounded-full bg-[#0F766E] text-xs font-bold text-white">
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
          PHẦN 2: KHUNG CHÀO MỪNG (TRÁI) & 3 CHỈ SỐ TỔNG QUAN (PHẢI)
          Minimal SaaS: hero gọn hơn ~25%, 3 chỉ số đồng bộ kích thước
      ===================================================================== */}
      <section
        className="relative overflow-hidden border-b border-[#D2E5E1] bg-gradient-to-br from-[#DCF2EE] via-[#E8F6F3] to-[#DFF0FA] py-6 sm:py-7"
        data-purpose="hero-and-metrics-section"
      >
        {/* Hiệu ứng ánh sáng nền kiểu Motivo */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-24 left-1/3 h-64 w-64 rounded-full bg-[#99F6E4]/35 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute right-10 -bottom-10 h-56 w-56 rounded-full bg-[#BAE6FD]/40 blur-3xl"
        />
        {/* Lưới chấm mảnh tạo chiều sâu, mờ dần về phía trái */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(#0F766E_0.8px,transparent_0.8px)] [background-size:18px_18px] opacity-[0.07] [mask-image:linear-gradient(to_left,black,transparent_70%)]"
        />

        <div className="relative mx-auto w-full max-w-6xl px-4 sm:px-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between lg:gap-10">
            {/* Bên trái: Ngày hôm nay + Lời chào với Tên nổi bật + Slogan ngắn gọn */}
            <div className="min-w-0 space-y-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-white/80 bg-white/60 px-2.5 py-1 text-xs font-medium text-[#37524F] capitalize backdrop-blur-xs">
                <span className="h-1.5 w-1.5 rounded-full bg-[#0D9488]" />
                {todayLabel}
              </span>
              <h1 className="text-2xl leading-tight font-bold tracking-tight text-[#0B1716] sm:text-[28px] lg:text-[32px]">
                {greeting()},{" "}
                <span className="bg-gradient-to-r from-[#0F766E] via-[#0D9488] to-[#0284C7] bg-clip-text font-bold text-transparent">
                  {user?.name || "bạn"}
                </span>
              </h1>
              <p className="max-w-lg text-sm leading-relaxed text-[#3A5754]">
                Không gian tri thức tách biệt — Tập trung tối đa, hiệu quả vượt trội.
              </p>
            </div>

            {/* Bên phải: 3 chỉ số tổng quan gộp trong một panel kính mờ */}
            <div className="grid w-full grid-cols-3 divide-x divide-[#DCEBE7] rounded-2xl border border-white/90 bg-white/75 py-3 shadow-[0_8px_30px_-12px_rgba(11,35,32,0.15)] backdrop-blur-md lg:w-auto lg:shrink-0">
              {[
                { label: "Workspace", value: String(workspaces.length), icon: <IconStatWorkspace /> },
                { label: "Tài liệu", value: String(totalDocs), icon: <IconStatDocuments /> },
                { label: "Dung lượng", value: totalSizeDisplay, icon: <IconStatStorage /> },
              ].map((stat) => (
                <div
                  key={stat.label}
                  className="flex min-w-0 items-center justify-center gap-3 px-3 sm:px-5 lg:min-w-[150px] lg:justify-start"
                >
                  <div className="hidden h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#DFF5F0] to-[#E0F0FB] text-[#0F766E] sm:flex">
                    {stat.icon}
                  </div>
                  <div className="min-w-0 text-center sm:text-left">
                    <div className="truncate text-lg leading-tight font-bold tracking-tight text-[#0B1716] tabular-nums">
                      {stat.value}
                    </div>
                    <div className="truncate text-xs font-medium text-[#5C7875]">
                      {stat.label}
                    </div>
                  </div>
                </div>
              ))}
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
        className="mx-auto w-full max-w-6xl flex-1 space-y-5 px-4 py-8 sm:px-6"
        data-purpose="recent-workspaces-section"
      >
        {/* Header của Phần 3 + Thanh Tìm kiếm & Sắp xếp */}
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              <h2 className="text-lg font-semibold tracking-tight text-[#0B1716] sm:text-xl">
                Không gian làm việc gần đây
              </h2>
              <span className="rounded-full bg-[#DFF5F0] px-2.5 py-0.5 text-xs font-semibold text-[#0F766E] tabular-nums">
                {filteredWorkspaces.length}
              </span>
            </div>
            <p className="mt-0.5 text-[13px] text-[#647D7A]">
              Chọn một không gian để tiếp tục học tập và hỏi đáp cùng AI.
            </p>
          </div>

          {/* Thanh Tìm kiếm & Nút Sắp xếp */}
          <div className="flex items-center gap-2">
            <div className="relative flex h-9 min-w-0 flex-1 items-center gap-2 rounded-full border border-[#C8DED9] bg-white px-3.5 shadow-2xs transition-all focus-within:border-[#0F766E] focus-within:ring-2 focus-within:ring-[#0F766E]/15 sm:w-56 sm:flex-none">
              {showSearchingSemantic ? (
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-[#0F766E]" />
              ) : (
                <Search className="h-3.5 w-3.5 shrink-0 text-[#647D7A]" />
              )}
              <input
                ref={searchInputRef}
                value={searchQuery}
                onChange={(e) => {
                  const next = e.target.value
                  setSearchQuery(next)
                  if (!next.trim()) {
                    setSemanticResults(null)
                    setSearchingSemantic(false)
                  }
                }}
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
                  className="inline-flex h-9 shrink-0 cursor-pointer items-center gap-1.5 rounded-full border border-[#C8DED9] bg-white px-3.5 text-xs font-semibold text-[#233D3A] shadow-2xs transition-colors hover:border-[#0F766E] hover:bg-[#F4FAF9]"
                  aria-label={`Sắp xếp: ${SORT_LABELS[sortOption]}`}
                >
                  <ArrowUpDown className="h-3.5 w-3.5 text-[#0F766E]" />
                  <span className="text-[#5C7875]">Sắp xếp:</span>
                  <span>{SORT_LABELS[sortOption]}</span>
                </button>
              }
            >
              <DropdownMenuLabel>Sắp xếp theo</DropdownMenuLabel>
              {(Object.keys(SORT_LABELS) as SortOption[]).map((opt) => (
                <DropdownMenuItem
                  key={opt}
                  icon={
                    <Check
                      className={cn(
                        "h-3.5 w-3.5",
                        sortOption === opt ? "text-[#0F766E]" : "opacity-0",
                      )}
                    />
                  }
                  onClick={() => setSortOption(opt)}
                >
                  {SORT_LABELS[opt]}
                </DropdownMenuItem>
              ))}
            </DropdownMenu>
          </div>
        </div>

        {/* Trạng thái không tìm thấy kết quả */}
        {searchQuery.trim() && !showSearchingSemantic && filteredWorkspaces.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-[#D5E6E2] bg-white px-6 py-10 text-center">
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-[#F2F9F7] text-[#0F766E]">
              <Search className="h-4.5 w-4.5" />
            </div>
            <h3 className="text-[15px] font-semibold text-[#0B1716]">
              Không tìm thấy “{searchQuery.trim()}”
            </h3>
            <p className="mt-1 text-[13px] text-[#647D7A]">
              Thử từ khóa khác hoặc tạo một Workspace mới.
            </p>
            <button
              type="button"
              onClick={() => {
                setSearchQuery("")
                setSemanticResults(null)
                setSearchingSemantic(false)
                searchInputRef.current?.focus()
              }}
              className="mt-4 inline-flex h-8 items-center rounded-full border border-[#C8DED9] px-4 text-xs font-semibold text-[#233D3A] transition-colors hover:border-[#0F766E] hover:bg-[#F4FAF9]"
            >
              Xóa tìm kiếm
            </button>
          </div>
        ) : null}

        {/* Lưới thẻ Workspace chuyên nghiệp */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 lg:gap-5">
          {filteredWorkspaces.map((w, idx) => {
            const wsDocs = documents.filter((d) => d.workspaceId === w.id)
            const wsConvs = conversations.filter((c) => c.workspaceId === w.id)
            const docCount = w.docCount ?? wsDocs.length
            const convCount = w.conversationCount ?? wsConvs.length

            return (
              <article
                key={w.id}
                onClick={() => handleEnterWorkspace(w, false)}
                className={cn(
                  "group relative flex h-full min-h-[184px] cursor-pointer flex-col rounded-2xl border border-[#DCEAE6] bg-white p-5",
                  "shadow-[0_1px_2px_rgba(11,25,23,0.04),0_6px_18px_-10px_rgba(11,25,23,0.08)]",
                  "transition-[transform,box-shadow,border-color] duration-300 ease-out hover:z-20 focus-within:z-20 hover:-translate-y-1 hover:border-[#0F766E]/35 hover:shadow-[0_18px_40px_-16px_rgba(15,118,110,0.28)]",
                )}
              >
                {/* Vạch nhấn gradient xuất hiện khi hover */}
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-x-6 top-0 h-[2px] rounded-full bg-gradient-to-r from-[#0F766E] via-[#0D9488] to-[#0284C7] opacity-0 transition-opacity duration-300 group-hover:opacity-100"
                />
                <div className="flex-1">
                  {/* Hàng trên: Icon + Tên Workspace (1 dòng) & thời gian cập nhật + Menu 3 chấm */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 flex-1 items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#E3F5F1] to-[#E2F0FA] text-[#0F6E66] ring-1 ring-[#D5E8E3] transition-all duration-300 group-hover:from-[#0F766E] group-hover:to-[#0D9488] group-hover:text-white group-hover:ring-transparent">
                        <WorkspaceGlyph category={w.category} index={idx} />
                      </div>
                      <div className="flex min-w-0 flex-1 flex-col">
                        <h3
                          className="truncate text-[15px] leading-snug font-semibold tracking-[-0.01em] text-[#0B1716] transition-colors group-hover:text-[#0F766E]"
                          title={w.name}
                        >
                          {w.name}
                        </h3>
                        <span className="text-xs text-[#6E8582]">
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
                        {authenticated && docCount > 0 ? (
                          <DropdownMenuItem
                            icon={<Sparkles className="h-3.5 w-3.5" />}
                            onClick={async () => {
                              toast({
                                title: "AI đang phân tích tài liệu...",
                                description: `Đang tổng hợp tiêu đề & mô tả cho "${w.name}".`,
                                tone: "info",
                              })
                              try {
                                const res = await generateWorkspaceMetadataApi(w.id)
                                if (res.workspace) {
                                  mergeWorkspaces([res.workspace])
                                  setSemanticResults((prev) =>
                                    prev
                                      ? prev.map((item) => (item.id === w.id ? res.workspace! : item))
                                      : null,
                                  )
                                  toast({
                                    title: res.source === "ai" ? "Đã cập nhật bằng AI" : "Đã cập nhật metadata",
                                    description: res.workspace.name,
                                    tone: res.source === "ai" ? "success" : "warning",
                                  })
                                }
                              } catch (err) {
                                toast({
                                  title: "Không thể tạo lại mô tả AI",
                                  description: err instanceof Error ? err.message : "Lỗi kết nối backend",
                                  tone: "error",
                                })
                              }
                            }}
                          >
                            Tạo lại tiêu đề &amp; mô tả AI
                          </DropdownMenuItem>
                        ) : null}
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

                  {/* Mô tả tối đa 2 dòng (title hiển thị đầy đủ khi hover) */}
                  <p
                    className="mt-3.5 line-clamp-2 min-h-[40px] text-[13px] leading-[1.55] text-[#526B68]"
                    title={w.description || undefined}
                  >
                    {w.description || "Không gian làm việc với tài liệu và trợ lý RAG."}
                  </p>
                </div>

                {/* Chân thẻ: Thông số gọn sạch bên trái + Nút "Mở" bên phải */}
                <div className="mt-4 flex items-center justify-between border-t border-[#EEF4F2] pt-3.5">
                  <div className="flex items-center gap-3 text-xs font-medium text-[#526B68] tabular-nums">
                    <span className="inline-flex items-center gap-1.5">
                      <FileText className="h-3.5 w-3.5 text-[#8AA29E]" />
                      {docCount} tài liệu
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <MessageSquare className="h-3.5 w-3.5 text-[#8AA29E]" />
                      {convCount} hội thoại
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleEnterWorkspace(w, false)
                    }}
                    className="group/btn inline-flex h-7 items-center gap-1 rounded-full bg-[#EEF7F5] px-3 text-xs font-semibold text-[#0F766E] transition-colors duration-300 group-hover:bg-[#0B1315] group-hover:text-white hover:!bg-[#0F766E]"
                  >
                    <span>Mở</span>
                    <ArrowRight className="h-3.5 w-3.5 transition-transform duration-300 group-hover:translate-x-0.5" />
                  </button>
                </div>
              </article>
            )
          })}

          {/* Thẻ Tạo Workspace mới */}
          <button
            type="button"
            disabled={creatingWs}
            onClick={() => void handleQuickCreateWorkspace()}
            className="group flex h-full min-h-[184px] cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed border-[#B2D0CA] bg-white/60 p-5 text-center transition-[transform,box-shadow,border-color,background-color] duration-200 ease-out hover:-translate-y-0.5 hover:border-[#0F766E] hover:bg-white hover:shadow-[0_12px_28px_-12px_rgba(15,118,110,0.22)] disabled:opacity-60"
          >
            <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl border border-[#D5E8E3] bg-[#F2F9F7] text-[#0F6E66] transition-colors duration-200 group-hover:border-[#0F766E] group-hover:bg-[#0F766E] group-hover:text-white">
              {creatingWs ? <Loader2 className="h-5 w-5 animate-spin" /> : <Plus className="h-5 w-5" />}
            </div>
            <h3 className="text-[15px] font-semibold text-[#0B1716]">
              {creatingWs ? "Đang tạo Workspace..." : "Tạo Workspace mới"}
            </h3>
            <p className="mt-1 max-w-[220px] text-[13px] leading-relaxed text-[#526B68]">
              Vào thẳng không gian và tải tài liệu để AI tự đặt tiêu đề, mô tả.
            </p>
          </button>
        </div>
      </main>

      {/* Footer tối giản kiểu Motivo */}
      <footer className="mt-auto border-t border-[#D5E6E2] bg-white py-5">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-4 text-xs text-[#647D7A] sm:flex-row sm:px-6">
          <div className="flex items-center gap-2">
            <span className="font-sans font-bold text-[#0B1716]">
              motivo<span className="text-[#0D9488]">.</span>
            </span>
            <span>— Không gian tri thức AI cá nhân</span>
          </div>
          <span>&copy; 2026 Motivo Workspace. All rights reserved.</span>
        </div>
      </footer>

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
