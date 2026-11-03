import { useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  Activity,
  ArrowRight,
  ArrowUpDown,
  Bot,
  BrainCircuit,
  ChevronRight,
  Clock,
  Database,
  FileCheck2,
  FileText,
  FolderKanban,
  FolderPlus,
  Folders,
  Languages,
  Layers,
  MessageSquare,
  Moon,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Sliders,
  Sparkles,
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
import { useAppStore } from "@/store/app-store"
import { formatBytes, greeting, relativeTime } from "@/utils/format"
import { hasDuplicateName } from "@/features/workspaces/workspace-utils"
import type { Workspace } from "@/types"
import { cn } from "@/utils/cn"

type SortOption = "updated" | "name" | "documents"

/**
 * Bảng màu pastel lấy cảm hứng từ thiết kế Motivo:
 * kết hợp sắc Mint (#E0F5F0), Ice Blue (#E3F2FD), Soft Lavender (#EDEBFD) và Deep Teal (#1D7A72)
 */
function getWorkspaceVisualMeta(category?: string, index = 0) {
  const key = category || ["Dự án", "Kỹ thuật", "Nghiên cứu", "Đại học"][index % 4]
  switch (key) {
    case "Kỹ thuật":
      return {
        iconBoxClass: "bg-[#E3F2FD] text-[#1565C0] border-[#BBDEFB]/60",
        Icon: Activity,
      }
    case "Nghiên cứu":
      return {
        iconBoxClass: "bg-[#EDEBFD] text-[#4F46E5] border-[#DDD6FE]/60",
        Icon: Bot,
      }
    case "Ngoại ngữ":
      return {
        iconBoxClass: "bg-[#E0F2F1] text-[#0F766E] border-[#B2DFDB]/60",
        Icon: Languages,
      }
    case "Đại học":
      return {
        iconBoxClass: "bg-[#DFF5F0] text-[#147D73] border-[#B6E9DF]/60",
        Icon: ShieldCheck,
      }
    case "Dự án":
      return {
        iconBoxClass: "bg-[#E0F5F0] text-[#16796F] border-[#BCECE0]/60",
        Icon: FolderKanban,
      }
    default:
      return {
        iconBoxClass: "bg-[#E4F5F2] text-[#1B7A70] border-[#C2EBE3]/60",
        Icon: Folders,
      }
  }
}

export function WorkspaceHubPage() {
  const navigate = useNavigate()
  const searchInputRef = useRef<HTMLInputElement>(null)

  const workspaces = useAppStore((s) => s.workspaces)
  const documents = useAppStore((s) => s.documents)
  const conversations = useAppStore((s) => s.conversations)
  const setCurrent = useAppStore((s) => s.setCurrentWorkspace)
  const createWorkspace = useAppStore((s) => s.createWorkspace)
  const updateWorkspace = useAppStore((s) => s.updateWorkspace)
  const deleteWorkspace = useAppStore((s) => s.deleteWorkspace)
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
  const readyDocs = documents.filter((d) => d.status === "ready").length
  const groundedPct = totalDocs > 0 ? Math.round((readyDocs / totalDocs) * 100) : 100

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

  // Actions
  const handleEnterWorkspace = (w: Workspace, toChat = false) => {
    setCurrent(w.id)
    toast({
      title: "Đã chọn không gian làm việc",
      description: w.name,
      tone: "info",
    })
    if (toChat) {
      const convInWs = conversations.find((c) => c.workspaceId === w.id)
      if (convInWs) {
        navigate(`/chat/${convInWs.id}`)
      } else {
        const newConv = createConversation(w.id)
        navigate(`/chat/${newConv.id}`)
      }
    } else {
      navigate("/dashboard")
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
    <div className="flex min-h-screen flex-col bg-[#F5FAF9] text-[#0B1716] antialiased selection:bg-[#BCECE0] selection:text-[#0B1716]">
      {/* =====================================================================
          PHẦN 1: THANH DASHBOARD (TOP HEADER)
          Gọn gàng, tinh tế theo phong cách Motivo:
          - Đã xóa "Tài liệu & Nguồn" (chỉ mở trong từng workspace)
          - Đã chuyển toàn bộ "Cài đặt hệ thống" vào droplist Hồ sơ người dùng
      ===================================================================== */}
      <header
        className="sticky top-0 z-50 border-b border-[#D8EAE6]/80 bg-[#EAF5F3]/85 backdrop-blur-md"
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
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#209688]/12 text-[#1D8A7D] transition-transform duration-200 group-hover:scale-105">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                className="h-5 w-5"
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
              motivo<span className="text-[#1D8A7D]">.</span>
            </span>
          </button>

          {/* Right Controls: Ollama Status + New Workspace CTA + User Profile Dropdown */}
          <div className="flex items-center gap-3">
            {/* Trạng thái AI Local */}
            <div className="hidden items-center gap-2 rounded-full border border-[#CBE4DF] bg-white/80 px-3 py-1.5 text-xs font-medium text-[#37524F] shadow-2xs sm:flex">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[#189E8C]" />
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
              className="group inline-flex items-center gap-2.5 rounded-full bg-[#0B1315] py-1.5 pr-2 pl-4 text-xs font-medium text-white shadow-sm transition-all duration-200 hover:bg-[#16272A]"
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
                  className="flex items-center gap-2 rounded-full border border-[#CBE4DF] bg-white p-1 pr-3 text-left shadow-2xs transition-colors hover:border-[#1D8A7D]/40 hover:bg-[#F4FAF9]"
                  title="Hồ sơ & Cài đặt hệ thống"
                >
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[#DFF5F0] text-xs font-bold text-[#147D73]">
                    SM
                  </div>
                  <span className="hidden text-xs font-semibold text-[#0B1716] sm:inline">
                    Sophie Moore
                  </span>
                </button>
              }
            >
              <DropdownMenuLabel>Sophie Moore · Quản trị viên</DropdownMenuLabel>
              <DropdownMenuItem
                icon={<Settings className="h-3.5 w-3.5" />}
                onClick={() => navigate("/settings")}
              >
                Cài đặt tài khoản
              </DropdownMenuItem>

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
            </DropdownMenu>
          </div>
        </div>
      </header>

      {/* =====================================================================
          PHẦN 2: KHUNG CHÀO MỪNG & THỐNG KÊ (HERO + STATS SECTION)
          Thiết kế theo bảng màu Mint/Ice-Blue của Motivo:
          - Đã xóa 2 nút "Nhập tài liệu" và "Mở Chatbot RAG"
          - Khung thống kê nguyên khối màu trắng bo tròn mềm mại với 4 chỉ số
      ===================================================================== */}
      <section
        className="relative overflow-hidden border-b border-[#DCECE9] bg-gradient-to-b from-[#E5F4F1] via-[#EEF8F6] to-[#F5FAF9] pt-10 pb-12"
        data-purpose="hero-and-metrics-section"
      >
        {/* Hiệu ứng ánh sáng nền kiểu Motivo */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-24 right-1/4 h-80 w-80 rounded-full bg-[#B9EFE4]/40 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute top-10 right-10 h-64 w-64 rounded-full bg-[#BEE3F8]/35 blur-3xl"
        />

        <div className="relative mx-auto max-w-6xl space-y-9 px-6">
          {/* Khung chào mừng */}
          <div className="max-w-2xl space-y-3">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/80 bg-white/75 px-3 py-1 text-[11px] font-medium text-[#355451] shadow-2xs backdrop-blur-xs">
              <span className="rounded-full bg-[#DFF5F0] px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-[#147D73]">
                HUB
              </span>
              <span>Không gian tri thức AI cá nhân đã sẵn sàng</span>
              <Sparkles className="h-3 w-3 text-[#1D8A7D]" />
            </div>

            <h1 className="font-editorial-serif text-4xl leading-[1.15] font-normal tracking-tight text-[#0B1716] sm:text-5xl">
              {greeting()}, Sophie.{" "}
              <span className="block italic text-[#23857C]">
                Làm việc thông minh hơn.
              </span>
            </h1>

            <p className="max-w-xl text-sm leading-relaxed text-[#4E6764] sm:text-[15px]">
              Mọi tài liệu, cuộc trò chuyện và công cụ ôn tập được tổ chức tách biệt trong từng
              Workspace riêng biệt — giúp bạn tập trung tối đa và đạt kết quả tốt nhất.
            </p>
          </div>

          {/* Thanh thống kê 4 cột kiểu Motivo (White rounded bar with pastel icons) */}
          <div className="grid grid-cols-1 divide-y divide-[#EBF3F1] rounded-3xl border border-white bg-white/95 p-6 shadow-[0_18px_50px_-15px_rgba(14,55,50,0.07)] backdrop-blur-xs sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-4 lg:divide-x">
            {/* Chỉ số 1: Không gian làm việc */}
            <div className="flex items-center gap-4 py-3 first:pt-0 sm:px-5 sm:py-2 first:sm:pl-2">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#DFF5F0] text-[#147D73]">
                <Folders className="h-5 w-5" />
              </div>
              <div>
                <div className="font-sans text-2xl font-bold tracking-tight text-[#0B1716] sm:text-3xl">
                  {workspaces.length}
                </div>
                <p className="text-xs font-medium text-[#607875]">
                  Workspace hoạt động
                </p>
              </div>
            </div>

            {/* Chỉ số 2: Tài liệu sẵn sàng */}
            <div className="flex items-center gap-4 py-3 sm:px-6 sm:py-2">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#E3F2FD] text-[#1565C0]">
                <FileCheck2 className="h-5 w-5" />
              </div>
              <div>
                <div className="flex items-baseline gap-2">
                  <span className="font-sans text-2xl font-bold tracking-tight text-[#0B1716] sm:text-3xl">
                    {totalDocs}
                  </span>
                  <span className="text-xs font-semibold text-[#18897E]">
                    ({groundedPct}%)
                  </span>
                </div>
                <p className="text-xs font-medium text-[#607875]">
                  Tài liệu đã lập chỉ mục
                </p>
              </div>
            </div>

            {/* Chỉ số 3: Đoạn trích tri thức */}
            <div className="flex items-center gap-4 py-3 sm:px-6 sm:py-2">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#DFF5F0] text-[#147D73]">
                <BrainCircuit className="h-5 w-5" />
              </div>
              <div>
                <div className="font-sans text-2xl font-bold tracking-tight text-[#0B1716] sm:text-3xl">
                  {formattedChunks}
                </div>
                <p className="text-xs font-medium text-[#607875]">
                  Đoạn trích tri thức (Chunks)
                </p>
              </div>
            </div>

            {/* Chỉ số 4: Bộ nhớ Offline */}
            <div className="flex items-center gap-4 py-3 last:pb-0 sm:px-6 sm:py-2 last:sm:pr-2">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#E4F4F2] text-[#17786E]">
                <Clock className="h-5 w-5" />
              </div>
              <div>
                <div className="font-sans text-2xl font-bold tracking-tight text-[#0B1716] sm:text-3xl">
                  {totalSizeDisplay}
                </div>
                <p className="text-xs font-medium text-[#607875]">
                  Bộ nhớ tri thức cục bộ
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* =====================================================================
          PHẦN 3: CÁC WORKSPACE GẦN ĐÂY (RECENT WORKSPACES SECTION)
          - Đã xóa ký hiệu ⌘K ở thanh tìm kiếm
          - Đã xóa các bộ lọc Tất cả, Đại học, Nghiên cứu, Kỹ thuật, Ngoại ngữ, Dự án, Cá nhân
      ===================================================================== */}
      <main
        className="mx-auto w-full max-w-6xl flex-1 space-y-6 px-6 py-10"
        data-purpose="recent-workspaces-section"
      >
        {/* Header của Phần 3 + Thanh Tìm kiếm & Sắp xếp */}
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <span className="text-[11px] font-bold uppercase tracking-widest text-[#1D8A7D]">
              WORKSPACES
            </span>
            <div className="mt-1 flex items-center gap-2.5">
              <h2 className="font-editorial-serif text-2xl font-normal text-[#0B1716] sm:text-3xl">
                Không gian làm việc gần đây
              </h2>
              <span className="rounded-full bg-[#DFF5F0] px-2.5 py-0.5 text-xs font-semibold text-[#147D73]">
                {filteredWorkspaces.length}
              </span>
            </div>
          </div>

          {/* Thanh Tìm kiếm (không có ⌘K) & Nút Sắp xếp */}
          <div className="flex flex-wrap items-center gap-3 sm:flex-nowrap">
            <div className="relative flex w-full items-center gap-2 rounded-full border border-[#D4E6E3] bg-white px-4 py-2 shadow-2xs transition-all focus-within:border-[#1D8A7D] focus-within:ring-2 focus-within:ring-[#1D8A7D]/15 sm:w-72">
              <Search className="h-4 w-4 shrink-0 text-[#6D8683]" />
              <input
                ref={searchInputRef}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full border-none bg-transparent font-sans text-xs text-[#0B1716] placeholder-[#829B98] outline-none focus:ring-0"
                placeholder="Tìm kiếm Workspace..."
                type="text"
              />
            </div>

            <DropdownMenu
              align="end"
              trigger={
                <button
                  type="button"
                  className="inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-full border border-[#D4E6E3] bg-white px-3.5 py-2 text-xs font-medium text-[#37524F] shadow-2xs transition hover:border-[#1D8A7D]/40 hover:bg-[#F2F9F8]"
                >
                  <ArrowUpDown className="h-3.5 w-3.5 text-[#1D8A7D]" />
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

        {/* Lưới thẻ Workspace */}
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
          {filteredWorkspaces.map((w, idx) => {
            const meta = getWorkspaceVisualMeta(w.category, idx)
            const wsDocs = documents.filter((d) => d.workspaceId === w.id)
            const wsConvs = conversations.filter((c) => c.workspaceId === w.id)
            const docCount = wsDocs.length
            const chunkCount = wsDocs.reduce((acc, d) => acc + (d.totalChunks || 0), 0)
            const sizeBytes = wsDocs.reduce((acc, d) => acc + (d.fileSize || 0), 0)
            const sizeDisplay = sizeBytes > 0 ? formatBytes(sizeBytes) : "0 MB"

            return (
              <article
                key={w.id}
                onClick={() => handleEnterWorkspace(w, false)}
                className="group flex cursor-pointer flex-col justify-between rounded-3xl border border-[#DCECE8] bg-white p-6 shadow-[0_10px_30px_-10px_rgba(11,25,23,0.05)] transition-all duration-300 hover:-translate-y-1 hover:border-[#23857C]/40 hover:shadow-[0_20px_40px_-15px_rgba(24,137,126,0.14)]"
              >
                <div className="space-y-4">
                  {/* Đầu thẻ: Icon Pastel + Thời gian cập nhật + Menu 3 chấm */}
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          "flex h-11 w-11 items-center justify-center rounded-2xl border transition-transform duration-200 group-hover:scale-105",
                          meta.iconBoxClass,
                        )}
                      >
                        <meta.Icon className="h-5 w-5" />
                      </div>
                      <div>
                        <span className="block text-[11px] font-medium text-[#6D8683]">
                          Cập nhật {relativeTime(w.updatedAt)}
                        </span>
                        <span className="mt-0.5 inline-flex items-center gap-1 text-[11px] font-semibold text-[#18897E]">
                          <span className="h-1.5 w-1.5 rounded-full bg-[#189E8C]" />
                          <span>{wsConvs.length} cuộc trò chuyện</span>
                        </span>
                      </div>
                    </div>

                    <div onClick={(e) => e.stopPropagation()}>
                      <DropdownMenu
                        align="end"
                        trigger={
                          <button
                            type="button"
                            className="rounded-full p-1.5 text-[#7A9490] transition hover:bg-[#F0F7F6] hover:text-[#0B1716]"
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

                  {/* Tên & Mô tả Workspace */}
                  <div>
                    <h3 className="text-base font-bold text-[#0B1716] transition-colors group-hover:text-[#18897E]">
                      {w.name}
                    </h3>
                    <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-[#58726F]">
                      {w.description || "Không gian làm việc với tài liệu và trợ lý RAG cá nhân."}
                    </p>
                  </div>

                  {/* Thông số tài liệu trong Workspace */}
                  <div className="flex flex-wrap gap-2 pt-1">
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-[#F1F8F6] px-2.5 py-1 text-[11px] font-medium text-[#37524F]">
                      <FileText className="h-3 w-3 text-[#1D8A7D]" />
                      <span>{docCount} tài liệu</span>
                    </span>
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-[#F1F8F6] px-2.5 py-1 text-[11px] font-medium text-[#37524F]">
                      <Layers className="h-3 w-3 text-[#1D8A7D]" />
                      <span>{chunkCount} Chunks</span>
                    </span>
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-[#F1F8F6] px-2.5 py-1 text-[11px] font-medium text-[#37524F]">
                      <Database className="h-3 w-3 text-[#1D8A7D]" />
                      <span>{sizeDisplay}</span>
                    </span>
                  </div>
                </div>

                {/* Chân thẻ: Mở Workspace / Hỏi đáp */}
                <div className="mt-5 flex items-center justify-between border-t border-[#EBF3F1] pt-3.5 text-xs">
                  <span className="font-medium text-[#58726F] transition-colors group-hover:text-[#0B1716]">
                    Vào không gian
                  </span>

                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleEnterWorkspace(w, true)
                    }}
                    className="group/btn inline-flex items-center gap-1.5 rounded-full bg-[#F0F9F7] px-3 py-1 font-semibold text-[#147D73] transition-colors hover:bg-[#0B1315] hover:text-white"
                  >
                    <span>Hỏi đáp AI</span>
                    <ChevronRight className="h-3.5 w-3.5 transition-transform group-hover/btn:translate-x-0.5" />
                  </button>
                </div>
              </article>
            )
          })}

          {/* Thẻ Tạo Workspace mới */}
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="group flex min-h-[230px] cursor-pointer flex-col items-center justify-center rounded-3xl border-2 border-dashed border-[#BDE0D9] bg-[#ECF7F5]/50 p-6 text-center transition-all duration-300 hover:border-[#1D8A7D] hover:bg-[#E4F4F1]"
          >
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-[#147D73] shadow-sm transition-all duration-200 group-hover:scale-110 group-hover:bg-[#0B1315] group-hover:text-white">
              <FolderPlus className="h-5 w-5" />
            </div>
            <h3 className="text-sm font-bold text-[#0B1716]">
              Tạo Workspace mới
            </h3>
            <p className="mt-1 max-w-[210px] text-xs leading-relaxed text-[#58726F]">
              Khởi tạo không gian độc lập cho môn học, dự án hoặc chủ đề nghiên cứu mới.
            </p>
            <span className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-[#0B1315] px-3.5 py-1.5 text-[11px] font-medium text-white shadow-2xs transition-transform group-hover:scale-105">
              <span>Bắt đầu ngay</span>
              <ArrowRight className="h-3 w-3" />
            </span>
          </button>
        </div>
      </main>

      {/* Footer tối giản kiểu Motivo */}
      <footer className="mt-auto border-t border-[#DCECE8] bg-white py-6">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-6 text-xs text-[#647D7A] sm:flex-row">
          <div className="flex items-center gap-2">
            <span className="font-sans font-bold text-[#0B1716]">
              motivo<span className="text-[#1D8A7D]">.</span>
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
          onSubmit={(e) => {
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

            const ws = createWorkspace(name, descInput.value.trim())
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
        onSubmit={(name, description) => {
          if (!editTarget) return
          updateWorkspace(editTarget.id, { name, description })
          toast({ title: "Đã cập nhật Workspace", tone: "success" })
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
        onConfirm={() => {
          if (!deleteTarget) return
          deleteWorkspace(deleteTarget.id)
          toast({ title: "Đã xóa Workspace", description: deleteTarget.name, tone: "info" })
          setDeleteTarget(null)
        }}
      />
    </div>
  )
}
