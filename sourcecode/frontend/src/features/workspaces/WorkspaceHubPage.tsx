import { useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  Activity,
  ArrowRight,
  ArrowUpDown,
  Bot,
  BrainCircuit,
  Clock,
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
 * Bảng màu nhận diện cho từng thẻ Workspace để tạo điểm nhấn thị giác rõ nét,
 * lấy cảm hứng từ sắc xanh Teal, Ice Blue, Indigo và Mint của Motivo.
 */
function getWorkspaceVisualMeta(category?: string, index = 0) {
  const key = category || ["Dự án", "Kỹ thuật", "Nghiên cứu", "Đại học"][index % 4]
  switch (key) {
    case "Kỹ thuật":
      return {
        accentBar: "from-[#0284C7] to-[#38BDF8]",
        iconBoxClass: "bg-[#0284C7] text-white shadow-sm shadow-[#0284C7]/25",
        badgeClass: "bg-[#E0F2FE] text-[#0369A1] border-[#BAE6FD]",
        Icon: Activity,
      }
    case "Nghiên cứu":
      return {
        accentBar: "from-[#4F46E5] to-[#818CF8]",
        iconBoxClass: "bg-[#4F46E5] text-white shadow-sm shadow-[#4F46E5]/25",
        badgeClass: "bg-[#EEF2FF] text-[#4338CA] border-[#C7D2FE]",
        Icon: Bot,
      }
    case "Ngoại ngữ":
      return {
        accentBar: "from-[#0D9488] to-[#2DD4BF]",
        iconBoxClass: "bg-[#0D9488] text-white shadow-sm shadow-[#0D9488]/25",
        badgeClass: "bg-[#CCFBF1] text-[#0F766E] border-[#99F6E4]",
        Icon: Languages,
      }
    case "Đại học":
      return {
        accentBar: "from-[#0F766E] to-[#14B8A6]",
        iconBoxClass: "bg-[#0F766E] text-white shadow-sm shadow-[#0F766E]/25",
        badgeClass: "bg-[#DFF5F0] text-[#0F766E] border-[#99F6E4]",
        Icon: ShieldCheck,
      }
    case "Dự án":
      return {
        accentBar: "from-[#115E59] to-[#0D9488]",
        iconBoxClass: "bg-[#115E59] text-white shadow-sm shadow-[#115E59]/25",
        badgeClass: "bg-[#E0F5F0] text-[#115E59] border-[#A7F3D0]",
        Icon: FolderKanban,
      }
    default:
      return {
        accentBar: "from-[#0D9488] to-[#34D399]",
        iconBoxClass: "bg-[#0D9488] text-white shadow-sm shadow-[#0D9488]/25",
        badgeClass: "bg-[#E4F5F2] text-[#0F766E] border-[#A7F3D0]",
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
      title: "Đã mở không gian làm việc",
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
    <div className="flex min-h-screen flex-col bg-[#EEF4F3] text-[#0B1716] antialiased selection:bg-[#BCECE0] selection:text-[#0B1716]">
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
          PHẦN 2: KHUNG CHÀO MỪNG (TRÁI) & 4 Ô THỐNG KÊ HÌNH VUÔNG 2x2 (PHẢI)
      ===================================================================== */}
      <section
        className="relative overflow-hidden border-b border-[#D2E5E1] bg-gradient-to-br from-[#DCF2EE] via-[#E8F6F3] to-[#DFF0FA] py-10"
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

        <div className="relative mx-auto max-w-6xl px-6">
          <div className="grid grid-cols-1 items-center gap-8 lg:grid-cols-12">
            {/* Bên trái: Lời chào với Tên nổi bật + Slogan ngắn gọn */}
            <div className="space-y-3.5 lg:col-span-7">
              <h1 className="font-editorial-serif text-4xl leading-[1.15] font-medium tracking-tight text-[#0B1716] sm:text-5xl">
                {greeting()},{" "}
                <span className="bg-gradient-to-r from-[#0F766E] via-[#0D9488] to-[#0284C7] bg-clip-text font-semibold italic text-transparent underline decoration-[#0D9488]/35 decoration-2 underline-offset-8">
                  Sophie
                </span>{" "}
                👋
              </h1>

              <p className="max-w-lg text-base font-medium leading-relaxed text-[#2C4A47] sm:text-lg">
                Không gian tri thức tách biệt — Tập trung tối đa, hiệu quả vượt trội.
              </p>
            </div>

            {/* Bên phải: 4 ô thống kê tối giản (Icon + ít chữ, kích thước nhỏ gọn 2x2) */}
            <div className="grid w-full max-w-[310px] grid-cols-2 gap-2.5 lg:col-span-5 lg:ml-auto">
              {/* Ô 1: Workspace */}
              <div className="flex items-center gap-2.5 rounded-xl border border-white/90 bg-white/90 px-3 py-2.5 shadow-xs backdrop-blur-xs">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#DFF5F0] text-[#0F766E]">
                  <Folders className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="font-sans text-base leading-tight font-bold text-[#0B1716]">
                    {workspaces.length}
                  </div>
                  <div className="truncate text-[11px] font-medium text-[#647D7A]">
                    Workspace
                  </div>
                </div>
              </div>

              {/* Ô 2: Tài liệu */}
              <div className="flex items-center gap-2.5 rounded-xl border border-white/90 bg-white/90 px-3 py-2.5 shadow-xs backdrop-blur-xs">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#E0F2FE] text-[#0284C7]">
                  <FileCheck2 className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="font-sans text-base leading-tight font-bold text-[#0B1716]">
                    {totalDocs}
                  </div>
                  <div className="truncate text-[11px] font-medium text-[#647D7A]">
                    Tài liệu
                  </div>
                </div>
              </div>

              {/* Ô 3: Chunks */}
              <div className="flex items-center gap-2.5 rounded-xl border border-white/90 bg-white/90 px-3 py-2.5 shadow-xs backdrop-blur-xs">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#EEF2FF] text-[#4F46E5]">
                  <BrainCircuit className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="font-sans text-base leading-tight font-bold text-[#0B1716]">
                    {formattedChunks}
                  </div>
                  <div className="truncate text-[11px] font-medium text-[#647D7A]">
                    Chunks
                  </div>
                </div>
              </div>

              {/* Ô 4: Bộ nhớ */}
              <div className="flex items-center gap-2.5 rounded-xl border border-white/90 bg-white/90 px-3 py-2.5 shadow-xs backdrop-blur-xs">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#CCFBF1] text-[#0F766E]">
                  <Clock className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="truncate font-sans text-base leading-tight font-bold text-[#0B1716]">
                    {totalSizeDisplay}
                  </div>
                  <div className="truncate text-[11px] font-medium text-[#647D7A]">
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
          Thiết kế thẻ có độ tương phản cao, nổi bật rõ trên nền trang:
          - Đã xóa chữ "Vào không gian"
          - Đã đổi "Hỏi đáp AI" thành nút "Mở" sắc nét
      ===================================================================== */}
      <main
        className="mx-auto w-full max-w-6xl flex-1 space-y-6 px-6 py-10"
        data-purpose="recent-workspaces-section"
      >
        {/* Header của Phần 3 + Thanh Tìm kiếm & Sắp xếp */}
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div className="flex items-center gap-3">
            <h2 className="font-editorial-serif text-2xl font-medium text-[#0B1716] sm:text-3xl">
              Không gian làm việc gần đây
            </h2>
            <span className="rounded-full bg-[#0F766E] px-2.5 py-0.5 text-xs font-bold text-white shadow-2xs">
              {filteredWorkspaces.length}
            </span>
          </div>

          {/* Thanh Tìm kiếm (không có ⌘K) & Nút Sắp xếp */}
          <div className="flex flex-wrap items-center gap-3 sm:flex-nowrap">
            <div className="relative flex w-full items-center gap-2 rounded-full border border-[#BDD6D1] bg-white px-4 py-2 shadow-xs transition-all focus-within:border-[#0F766E] focus-within:ring-2 focus-within:ring-[#0F766E]/15 sm:w-72">
              <Search className="h-4 w-4 shrink-0 text-[#526E6B]" />
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
                  className="inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-full border border-[#BDD6D1] bg-white px-3.5 py-2 text-xs font-semibold text-[#233D3A] shadow-xs transition hover:border-[#0F766E] hover:bg-[#F4FAF9]"
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

        {/* Lưới thẻ Workspace nổi bật */}
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {filteredWorkspaces.map((w, idx) => {
            const meta = getWorkspaceVisualMeta(w.category, idx)
            const wsDocs = documents.filter((d) => d.workspaceId === w.id)
            const wsConvs = conversations.filter((c) => c.workspaceId === w.id)
            const docCount = wsDocs.length

            return (
              <article
                key={w.id}
                onClick={() => handleEnterWorkspace(w, false)}
                className="group relative flex cursor-pointer flex-col justify-between overflow-hidden rounded-3xl border border-[#C3DDD8] bg-white p-6 shadow-[0_14px_34px_-10px_rgba(11,35,32,0.10),0_2px_6px_rgba(11,35,32,0.04)] transition-all duration-300 hover:-translate-y-1.5 hover:border-[#0F766E] hover:shadow-[0_24px_48px_-12px_rgba(15,118,110,0.22)]"
              >
                {/* Dải màu nhấn phía trên thẻ giúp thẻ tách biệt hẳn khỏi nền */}
                <div
                  className={cn(
                    "absolute inset-x-0 top-0 h-1.5 bg-gradient-to-r",
                    meta.accentBar,
                  )}
                />

                <div className="space-y-4 pt-1">
                  {/* Đầu thẻ: Icon đậm nổi bật + Nhãn thời gian + Menu 3 chấm */}
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3.5">
                      <div
                        className={cn(
                          "flex h-12 w-12 items-center justify-center rounded-2xl transition-transform duration-200 group-hover:scale-105",
                          meta.iconBoxClass,
                        )}
                      >
                        <meta.Icon className="h-5 w-5" />
                      </div>
                      <div>
                        <span
                          className={cn(
                            "inline-flex items-center rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider",
                            meta.badgeClass,
                          )}
                        >
                          {w.category || "Cá nhân"}
                        </span>
                        <span className="mt-1 block text-[11px] font-medium text-[#5C7875]">
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
                            className="rounded-full p-1.5 text-[#647D7A] transition hover:bg-[#EAF4F2] hover:text-[#0B1716]"
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
                    <h3 className="text-[17px] leading-snug font-bold text-[#091514] transition-colors group-hover:text-[#0F766E]">
                      {w.name}
                    </h3>
                    <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-[#4A6663]">
                      {w.description || "Không gian làm việc với tài liệu và trợ lý RAG cá nhân."}
                    </p>
                  </div>
                </div>

                {/* Chân thẻ: Thông số gọn bên trái & Nút "Mở" nổi bật bên phải (Đã xóa "Vào không gian") */}
                <div className="mt-6 flex items-center justify-between border-t border-[#E6F0EE] pt-4">
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center gap-1.5 rounded-lg bg-[#EFF7F5] px-2.5 py-1 text-xs font-semibold text-[#1E3A37]">
                      <FileText className="h-3.5 w-3.5 text-[#0F766E]" />
                      <span>{docCount} tài liệu</span>
                    </span>
                    <span className="inline-flex items-center gap-1.5 rounded-lg bg-[#EFF7F5] px-2.5 py-1 text-xs font-semibold text-[#1E3A37]">
                      <MessageSquare className="h-3.5 w-3.5 text-[#0F766E]" />
                      <span>{wsConvs.length} hội thoại</span>
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleEnterWorkspace(w, false)
                    }}
                    className="group/btn inline-flex items-center gap-1.5 rounded-full bg-[#0B1315] px-4 py-1.5 text-xs font-semibold text-white shadow-xs transition-all duration-200 hover:bg-[#0F766E] hover:shadow-md"
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
            className="group flex min-h-[230px] cursor-pointer flex-col items-center justify-center rounded-3xl border-2 border-dashed border-[#9CCAC1] bg-white/75 p-6 text-center shadow-xs transition-all duration-300 hover:-translate-y-1 hover:border-[#0F766E] hover:bg-white hover:shadow-lg"
          >
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-[#DFF5F0] text-[#0F766E] shadow-xs transition-all duration-200 group-hover:scale-110 group-hover:bg-[#0F766E] group-hover:text-white">
              <FolderPlus className="h-5 w-5" />
            </div>
            <h3 className="text-base font-bold text-[#0B1716]">
              Tạo Workspace mới
            </h3>
            <p className="mt-1 max-w-[220px] text-xs leading-relaxed text-[#4A6663]">
              Khởi tạo không gian độc lập cho môn học, dự án hoặc chủ đề nghiên cứu mới.
            </p>
            <span className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-[#0B1315] px-4 py-1.5 text-xs font-semibold text-white shadow-xs transition-colors group-hover:bg-[#0F766E]">
              <span>Bắt đầu ngay</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </span>
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
